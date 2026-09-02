"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  getSourceBandWaveform,
  getSourceBeepOnsets,
  getSourceWaveform,
} from "@/lib/api";
import type { BeepOnsets, Waveform } from "@/lib/types";

/**
 * 원본 전체 파형 (docs/16) — 3분 원본을 통째로 보고 이벤트 위치를 눈으로 찾는 용도.
 * 세그먼트 미니 파형(60칸)과 달리 1200칸으로 촘촘히 그린다.
 *
 * 피크 표시(2026-08-28 변경): 예전에는 이 컴포넌트가 전대역 파형에서
 * "평균+2.5σ"로 직접 계산했는데, 저역 소음(엔진·환기팬·음악)에 반응해
 * 문 닫힘·차량 통과 같은 광대역 충격음만 찍히고 정작 비프음은 놓쳤다.
 * 이제 대역통과 검출기(band_beep_detector)의 결과를 그대로 쓴다 —
 * 파형과 비프 대역 탭이 **같은 지점**을 가리키게 된다.
 *
 * band 모드(2026-09-01 추가, docs/16 §7 추가8): `band`가 true면 전대역
 * 대신 **대역통과 파형**(1.8~2.2kHz 엔벨로프, 정규화)을 그린다. 비프 대역
 * 탭에서만 켜서 위(파형)·아래(스펙트로그램)·▲가 같은 대역을 가리키게
 * 한다. **기본값 false — 기존 두 탭의 표시는 이전과 100% 동일하다.**
 */
export function SourceWaveform({
  sourceId,
  width = 760,
  height = 120,
  showPeaks = true,
  band = false,
}: {
  sourceId: number;
  width?: number;
  height?: number;
  showPeaks?: boolean;
  /** true면 대역통과 파형(정규화). 기본 false = 기존 전대역 절대 스케일. */
  band?: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [wave, setWave] = useState<Waveform | null>(null);
  const [peakAbs, setPeakAbs] = useState<number | null>(null);
  const [onsets, setOnsets] = useState<BeepOnsets | null>(null);
  const [failed, setFailed] = useState(false);
  const [hover, setHover] = useState<{ x: number; t: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setWave(null);
    setFailed(false);
    setPeakAbs(null);
    const load = band
      ? getSourceBandWaveform(sourceId).then((b) => {
          if (!cancelled) setPeakAbs(b.peak_abs);
          return {
            segment_id: sourceId,
            duration_sec: b.duration_sec,
            peaks: b.peaks,
          } as Waveform;
        })
      : getSourceWaveform(sourceId);
    load
      .then((w) => !cancelled && setWave(w))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [sourceId, band]);

  useEffect(() => {
    if (!showPeaks) return;
    let cancelled = false;
    // 검출 실패는 파형 표시 자체를 막지 않는다 — 표식만 안 뜬다.
    getSourceBeepOnsets(sourceId)
      .then((o) => !cancelled && setOnsets(o))
      .catch(() => !cancelled && setOnsets(null));
    return () => {
      cancelled = true;
    };
  }, [sourceId, showPeaks]);

  /** 검출된 비프음 위치 → 파형 칸 인덱스로 변환. */
  const peaks = useMemo(() => {
    if (!wave || !showPeaks || !onsets || wave.duration_sec <= 0) return [];
    const n = wave.peaks.length;
    return onsets.onsets_sec.map((sec) => ({
      index: Math.min(n - 1, Math.round((sec / wave.duration_sec) * n)),
      sec,
    }));
  }, [wave, showPeaks, onsets]);

  useEffect(() => {
    if (!wave || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);

    const mid = height / 2;
    const n = wave.peaks.length;
    const barW = width / n;

    // 중앙 기준선 (recessive)
    ctx.strokeStyle = "#d5e5ee";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, mid);
    ctx.lineTo(width, mid);
    ctx.stroke();

    // 파형 — 기존(전대역)은 절대 스케일 유지, band 모드는 정규화값을 그대로 쓴다.
    ctx.fillStyle = band ? "#3f7f6f" : "#6b93c4";
    for (let i = 0; i < n; i++) {
      const h = Math.max(wave.peaks[i] > 0.004 ? 1 : 0.5, wave.peaks[i] * (height - 4));
      ctx.fillRect(i * barW, mid - h / 2, Math.max(barW * 0.9, 0.5), h);
    }

    // 피크 후보 표식 (위쪽 삼각형 + 세로 점선)
    if (showPeaks) {
      for (const pk of peaks) {
        const x = pk.index * barW + barW / 2;
        ctx.fillStyle = "#c39344";
        ctx.beginPath();
        ctx.moveTo(x, 2);
        ctx.lineTo(x - 4, 9);
        ctx.lineTo(x + 4, 9);
        ctx.closePath();
        ctx.fill();
        ctx.strokeStyle = "rgba(195, 147, 68, 0.35)";
        ctx.setLineDash([2, 3]);
        ctx.beginPath();
        ctx.moveTo(x, 9);
        ctx.lineTo(x, height);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }
  }, [wave, peaks, width, height, showPeaks, band]);

  if (failed) {
    return <span className="text-xs text-content-subtle">파형 없음</span>;
  }
  if (wave === null) {
    return (
      <div
        className="animate-pulse rounded bg-surface-muted"
        style={{ width, height }}
        aria-hidden
      />
    );
  }

  return (
    <div className="relative" style={{ width }}>
      <canvas
        ref={canvasRef}
        role="img"
        aria-label={
          band
            ? `원본 대역통과 파형 1.8~2.2kHz (${wave.duration_sec.toFixed(0)}초)`
            : `원본 전체 파형 (${wave.duration_sec.toFixed(0)}초)`
        }
        className="rounded border border-border"
        style={{ width, height }}
        onMouseMove={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          const x = e.clientX - r.left;
          setHover({ x, t: (x / width) * wave.duration_sec });
        }}
        onMouseLeave={() => setHover(null)}
      />
      {hover && (
        <div
          className="pointer-events-none absolute top-0 rounded bg-content px-1.5 py-0.5 text-xs text-surface-card"
          style={{ left: Math.min(hover.x + 6, width - 60) }}
        >
          {hover.t.toFixed(1)}초
        </div>
      )}
      <div className="mt-1 flex justify-between text-xs text-content-subtle">
        <span>0초</span>
        {showPeaks && onsets !== null && (
          <span className="text-status-warn">
            ▲ 비프음 {peaks.length}곳 (1.8~2.2kHz 대역 검출)
          </span>
        )}
        <span>{wave.duration_sec.toFixed(0)}초</span>
      </div>
      {band && peakAbs !== null && (
        <p className="mt-0.5 text-xs text-content-subtle">
          세로는 이 파일 안에서만 정규화된 값입니다(파일 간 크기 비교 불가).
          실제 최대 진폭 {peakAbs.toExponential(2)} — 절대 크기는 &quot;실제
          크기&quot; 탭에서 보세요.
        </p>
      )}
    </div>
  );
}
