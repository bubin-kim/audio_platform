"use client";

import { useEffect, useState } from "react";

import { getSegmentWaveform } from "@/lib/api";

/**
 * 세그먼트 미니 파형 — 재생 없이 커팅 결과를 눈으로 비교하는 용도.
 * peaks는 풀스케일 기준 절대값(백엔드에서 정규화 안 함)이라
 * 행 간 파형 높이를 그대로 비교할 수 있다. 색은 토큰(accent)만 사용.
 */
export function SegmentWaveform({
  segmentId,
  width = 120,
  height = 28,
}: {
  segmentId: number;
  width?: number;
  height?: number;
}) {
  const [peaks, setPeaks] = useState<number[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getSegmentWaveform(segmentId)
      .then((w) => !cancelled && setPeaks(w.peaks))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [segmentId]);

  if (failed) {
    return <span className="text-xs text-content-subtle">파형 없음</span>;
  }
  if (peaks === null) {
    return (
      <div
        className="animate-pulse rounded bg-surface-muted"
        style={{ width, height }}
        aria-hidden
      />
    );
  }

  const mid = height / 2;
  const barPitch = width / peaks.length;
  const barW = Math.max(1, barPitch - 1); // 막대 사이 1px 여백 (thin marks)

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="세그먼트 파형"
      className="text-accent"
    >
      {/* 중앙 기준선 — recessive (옅게) */}
      <line
        x1={0}
        y1={mid}
        x2={width}
        y2={mid}
        strokeWidth={1}
        className="stroke-border"
      />
      {peaks.map((p, i) => {
        // 절대 스케일 유지 + 소리가 있으면 최소 1px은 보이게
        const h = Math.max(p > 0.004 ? 1 : 0.5, p * (height - 2));
        return (
          <rect
            key={i}
            x={i * barPitch}
            y={mid - h / 2}
            width={barW}
            height={h}
            rx={0.5}
            fill="currentColor"
          />
        );
      })}
    </svg>
  );
}
