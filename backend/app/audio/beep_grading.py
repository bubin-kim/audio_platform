"""비프음 신뢰도 등급 — 여러 특징을 함께 보고 판정한다 (순수 로직, P2).

**왜 다중 특징인가** (청취 검증 20개, 2026-09-13):
기존 등급은 **지문 개수 하나**만 봤는데, 블라인드 청취 결과 절반만 맞았다.

| 지문 개수 | 실제 들림 | 안 들림 |
|---|---|---|
| 22개 이상 | 4 | 0 |
| 9개 | 0 | **1** ← 지문이 많은데 비프음 아님 |
| 2~3개 | 2 | 2 |
| 1개 | 3 | 1 |
| 0개 | **2** ← 지문 0인데 들림 | 3 |

- **지문 9개인데 안 들림**: 2kHz 근처에서 지속되는 기계음(환기팬 등)이
  스캔마다 걸려 지문이 쌓인 경우. 개수만 보면 진짜처럼 보인다.
- **지문 0개인데 들림**: 신호가 약해 PSD 최대 주파수가 안 잡힌 경우.

즉 **개수는 "얼마나 많이 걸렸나"일 뿐 "비프음다운가"를 말하지 않는다.**
그래서 비프음의 물리적 특성을 함께 본다.

**비프음의 특성** (실측):
  - 주파수: 1992~2004Hz의 좁은 순음 (표준편차 2.9Hz)
  - 순음성: 15~25dB (배경 소음은 0~13dB)
  - 지속시간: 약 180ms (175~189ms)
  - 시작: 급격히 상승 (지속음인 기계음과 구분되는 지점)

등급 기준은 **청취 정답으로 검증해야 확정된다.** 현재 가중치는 위 실측
분포에서 도출한 초안이며, `evaluate_against_listening()`으로 정답 대비
성능을 측정할 수 있게 해두었다.
"""

from dataclasses import dataclass
from typing import Any, Literal

Grade = Literal["high", "medium", "low", "none"]

# 비프음 지문 주파수 (실측 30표본: 중앙 2003.9Hz, sd 2.9Hz)
FINGERPRINT_HZ = 2004.0
FINGERPRINT_TOL_HZ = 60.0  # 이 범위를 벗어나면 비프음으로 보지 않는다

# 실측 기반 기준값
TONALITY_STRONG_DB = 15.0   # 진짜 비프음 15~25dB
TONALITY_WEAK_DB = 8.0      # 이하면 배경 소음일 가능성 높음
DURATION_MIN_MS = 60.0      # 너무 짧으면 순간적 잡음
DURATION_MAX_MS = 600.0     # 너무 길면 지속음(기계음)


@dataclass
class BeepFeatures:
    """한 검출 지점의 특징 묶음."""

    n_hits: int                      # 지문 매칭 횟수
    tonality_db: float | None = None  # 순음성
    peak_hz: float | None = None      # PSD 최대 주파수
    duration_ms: float | None = None  # 지속시간

    def freq_error_hz(self) -> float | None:
        if self.peak_hz is None:
            return None
        return abs(self.peak_hz - FINGERPRINT_HZ)


def _score(f: BeepFeatures) -> tuple[float, list[str]]:
    """특징들을 0~1 점수로 합산한다. (점수, 근거) 반환."""
    score = 0.0
    reasons: list[str] = []

    # ① 지문 개수 — 많을수록 좋지만 단독으로는 못 믿는다(위 docstring)
    if f.n_hits >= 22:
        score += 0.45
        reasons.append(f"지문 {f.n_hits}회(매우 많음)")
    elif f.n_hits >= 8:
        score += 0.30
        reasons.append(f"지문 {f.n_hits}회")
    elif f.n_hits >= 2:
        score += 0.18
        reasons.append(f"지문 {f.n_hits}회(적음)")
    elif f.n_hits == 1:
        score += 0.08
        reasons.append("지문 1회")

    # ② 순음성 — 비프음(좁은 순음)과 광대역 소음을 가르는 핵심 지표
    if f.tonality_db is not None:
        if f.tonality_db >= TONALITY_STRONG_DB:
            score += 0.35
            reasons.append(f"순음성 {f.tonality_db:.1f}dB(강함)")
        elif f.tonality_db >= TONALITY_WEAK_DB:
            score += 0.15
            reasons.append(f"순음성 {f.tonality_db:.1f}dB")
        else:
            score -= 0.15
            reasons.append(f"순음성 {f.tonality_db:.1f}dB(낮음 — 소음 의심)")

    # ③ 주파수 정확도 — 지문 대역을 크게 벗어나면 다른 소리다
    err = f.freq_error_hz()
    if err is not None:
        if err <= 20:
            score += 0.20
            reasons.append(f"주파수 {f.peak_hz:.0f}Hz(정확)")
        elif err <= FINGERPRINT_TOL_HZ:
            score += 0.08
            reasons.append(f"주파수 {f.peak_hz:.0f}Hz")
        else:
            score -= 0.20
            reasons.append(f"주파수 {f.peak_hz:.0f}Hz(대역 밖)")

    # ④ 지속시간 — 비프음은 ~180ms. 너무 길면 지속음(기계음) 의심
    if f.duration_ms is not None:
        if DURATION_MIN_MS <= f.duration_ms <= DURATION_MAX_MS:
            score += 0.10
            reasons.append(f"지속 {f.duration_ms:.0f}ms")
        else:
            score -= 0.10
            reasons.append(f"지속 {f.duration_ms:.0f}ms(비정상)")

    return max(0.0, min(1.0, score)), reasons


def grade_beep(features: BeepFeatures) -> dict[str, Any]:
    """검출 지점 하나의 신뢰도 등급을 매긴다.

    Returns:
        {"grade", "score", "reasons"}
    """
    score, reasons = _score(features)
    if score >= 0.70:
        grade: Grade = "high"
    elif score >= 0.45:
        grade = "medium"
    elif score >= 0.20:
        grade = "low"
    else:
        grade = "none"
    return {"grade": grade, "score": round(score, 3), "reasons": reasons}


def grade_legacy(n_hits: int) -> Grade:
    """기존 방식(지문 개수 단독) — 비교·회귀 확인용으로 남긴다."""
    if n_hits >= 4:
        return "high"
    if n_hits >= 2:
        return "medium"
    if n_hits == 1:
        return "low"
    return "none"


def evaluate_against_listening(
    items: list[tuple[BeepFeatures, bool]],
) -> dict[str, Any]:
    """청취 정답 대비 성능을 측정한다.

    Args:
        items: (특징, 실제로 들렸는가) 쌍의 목록

    Returns:
        새 방식과 기존 방식의 정확도 비교
    """
    if not items:
        return {"n": 0}

    def _acc(predict) -> dict[str, Any]:
        tp = fp = tn = fn = 0
        for feat, heard in items:
            pred = predict(feat)
            if pred and heard:
                tp += 1
            elif pred and not heard:
                fp += 1
            elif not pred and not heard:
                tn += 1
            else:
                fn += 1
        total = tp + fp + tn + fn
        return {
            "accuracy": round((tp + tn) / total, 3) if total else 0.0,
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        }

    return {
        "n": len(items),
        "new": _acc(lambda f: grade_beep(f)["grade"] in ("high", "medium")),
        "legacy": _acc(lambda f: grade_legacy(f.n_hits) in ("high", "medium")),
    }
