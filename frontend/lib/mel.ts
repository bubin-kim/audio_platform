/**
 * 멜 스케일 ↔ 주파수 변환 (docs/16).
 *
 * 백엔드가 librosa 기본값(Slaney 멜)으로 스펙트로그램을 만들므로, 축 눈금을
 * 정확한 위치에 찍으려면 같은 공식을 써야 한다. 선형 보간으로 근사하면
 * 저음 쪽이 크게 어긋난다 (2kHz가 전체 높이의 8%가 아니라 41% 지점).
 *
 * Slaney 방식: 1kHz까지는 선형(66.67 mel/kHz), 그 위는 로그.
 */

const F_MIN = 0.0;
const F_SP = 200.0 / 3; // 선형 구간 기울기 (mel per Hz)
const MIN_LOG_HZ = 1000.0;
const MIN_LOG_MEL = (MIN_LOG_HZ - F_MIN) / F_SP;
const LOGSTEP = Math.log(6.4) / 27.0;

export function hzToMel(hz: number): number {
  if (hz < MIN_LOG_HZ) return (hz - F_MIN) / F_SP;
  return MIN_LOG_MEL + Math.log(hz / MIN_LOG_HZ) / LOGSTEP;
}

export function melToHz(mel: number): number {
  if (mel < MIN_LOG_MEL) return F_MIN + F_SP * mel;
  return MIN_LOG_HZ * Math.exp(LOGSTEP * (mel - MIN_LOG_MEL));
}

/**
 * 주파수(Hz) → 스펙트로그램 세로 위치 비율 (0=바닥/저음, 1=천장/고음).
 *
 * 캔버스는 nMels개 행을 그리고 CSS로 늘리므로, 눈금은 **행의 중심**에 와야 한다.
 * 빈 i의 중심은 전체 높이의 (i + 0.5) / nMels 지점이다 — 이 보정을 빼면
 * 눈금이 한 행씩 밀려 보인다(실측: 500Hz 눈금이 500Hz 줄 아래에 찍힘).
 */
export function hzToRatio(hz: number, fmax: number, nMels = 96): number {
  const binPos = (hzToMel(hz) / hzToMel(fmax)) * (nMels - 1); // 0-based 빈 위치
  return (binPos + 0.5) / nMels;
}

/** 표시할 눈금 후보 — fmax 안에 드는 것만 고른다. 사람이 읽기 좋은 값들. */
const TICK_CANDIDATES = [
  100, 200, 500, 1000, 2000, 4000, 8000, 16000, 24000,
];

export function pickFrequencyTicks(fmax: number, maxTicks = 6): number[] {
  const inRange = TICK_CANDIDATES.filter((hz) => hz <= fmax * 0.98);
  if (inRange.length <= maxTicks) return inRange;
  // 너무 많으면 균등하게 솎아낸다 (양 끝은 유지)
  const step = Math.ceil(inRange.length / maxTicks);
  const picked = inRange.filter((_, i) => i % step === 0);
  const last = inRange[inRange.length - 1];
  if (picked[picked.length - 1] !== last) picked.push(last);
  return picked;
}

/** 눈금 라벨 — 1000 이상은 kHz로 짧게. */
export function formatHz(hz: number): string {
  if (hz >= 1000) {
    const k = hz / 1000;
    return `${Number.isInteger(k) ? k : k.toFixed(1)}k`;
  }
  return String(hz);
}
