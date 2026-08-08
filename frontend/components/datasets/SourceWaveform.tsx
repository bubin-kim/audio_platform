"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { getSourceWaveform } from "@/lib/api";
import type { Waveform } from "@/lib/types";

/**
 * 원본 전체 파형 (docs/16) — 3분 원본을 통째로 보고 이벤트 위치를 눈으로 찾는 용도.
 * 세그먼트 미니 파형(60칸)과 달리 1200칸으로 촘촘히 그린다.
 *
 * 피크 표시: 평균 + k×표준편차를 넘는 지점에 표식을 찍는다(사용자 요청).
 * 자동 검출이 완벽하지 않으므로 "후보"일 뿐이며, 최종 판단은 사람이 한다.
 */
export function SourceWaveform({
  sourceId,
  width = 760,
  height = 120,
  showPeaks = true,
  peakSigma = 2.5,
}: {
  sourceId: number;
  width?: number;
  height?: number;
  showPeaks?: boolean;
  peakSigma?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [wave, setWave] = useState<Waveform | null>(null);
  const [failed, setFailed] = useState(false);
  const [hover, setHover] = useState<{ x: number; t: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    getSourceWaveform(sourceId)
      .then((w) => !cancelled && setWave(w))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [sourceId]);

  /** 평균 초과 피크 후보 — 인접한 것은 하나로 묶는다. */
  const peaks = useMemo(() => {
    if (!wave || !showPeaks) return [];
    const p = wave.peaks;
    const mean = p.reduce((a, b) => a + b, 0) / p.length;
    const sd = Math.sqrt(
      p.reduce((a, b) => a + (b - mean) ** 2, 0) / p.length,
    );
    const th = mean + peakSigma * sd;
    const found: { index: number; value: number }[] = [];
    let runStart = -1;
    let runBest = { index: -1, value: -1 };
    for (let i = 0; i < p.length; i++) {
      if (p[i] > th) {
        if (runStart < 0) {
          runStart = i;
          runBest = { index: i, value: p[i] };
        } else if (p[i] > runBest.value) {
          runBest = { index: i, value: p[i] };
        }
      } else if (runStart >= 0) {
        // 인접 병합: 마지막 후보와 가까우면(전체의 1% 이내) 건너뛴다
        const last = found[found.length - 1];
        if (!last || runBest.index - last.index > p.length * 0.01) {
          found.push(runBest);
        }
        runStart = -1;
      }
    }
    if (runStart >= 0) found.push(runBest);
    return found;
  }, [wave, showPeaks, peakSigma]);

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

    // 파형 — 절대 스케일 유지
    ctx.fillStyle = "#6b93c4";
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
  }, [wave, peaks, width, height, showPeaks]);

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
        aria-label={`원본 전체 파형 (${wave.duration_sec.toFixed(0)}초)`}
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
        {showPeaks && (
          <span className="text-status-warn">
            ▲ 피크 후보 {peaks.length}곳 (평균+{peakSigma}σ 초과)
          </span>
        )}
        <span>{wave.duration_sec.toFixed(0)}초</span>
      </div>
    </div>
  );
}
