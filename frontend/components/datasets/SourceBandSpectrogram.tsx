"use client";

import { useEffect, useRef, useState } from "react";

import { getSourceBandSpectrogram, getSourceBeepOnsets } from "@/lib/api";
import type { BandSpectrogram, BeepOnsets } from "@/lib/types";
import config from "@/tailwind.config";

/**
 * 주파수 크롭 스펙트로그램(신규, 표시 전용) — 1500~2500Hz만 세로 전체 높이에
 * 확대해서 그린다. 기존 두 탭(실제 크기/배경 제거, Spectrogram.tsx)과 완전히
 * 별개 컴포넌트·별개 API — 그쪽 로직은 이 파일이 전혀 건드리지 않는다.
 *
 * 대역통과 기반 비프음 검출(band_beep_detector.py) 결과를 빨간 세로선으로
 * 겹쳐 그리고, 검출 검증 통계(개수·오프셋·간격)를 텍스트로 함께 보여준다 —
 * 오프셋이 5초 근방에 몰려 있고 표준편차가 작으면 검출이 맞았다는 신호,
 * 흩어져 있으면 파라미터(k·대역폭)를 의심하라는 신호(녹음 설계: 초의
 * 일의 자리 5초에 키를 눌렀으므로 onset % 10 ≈ 5초여야 한다).
 */

const SPECTRO = (config.theme?.extend?.colors as Record<string, unknown>)
  ?.spectro as Record<string, string>;
const STOPS = Object.keys(SPECTRO)
  .sort((a, b) => Number(a) - Number(b))
  .map((k) => SPECTRO[k]);

function hexToRgb(hex: string): [number, number, number] {
  const v = parseInt(hex.slice(1), 16);
  return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
}

/** 0~255 → RGB 룩업 테이블. 기존 Spectrogram.tsx와 같은 viridis 램프를
 * 재사용하되, 이쪽은 0~255 스케일(top_db 상대값)이라 테이블 크기만 다르다. */
function buildLut(): Uint8Array {
  const rgb = STOPS.map(hexToRgb);
  const lut = new Uint8Array(256 * 3);
  for (let q = 0; q <= 255; q++) {
    const t = (q / 255) * (rgb.length - 1);
    const i = Math.min(Math.floor(t), rgb.length - 2);
    const f = t - i;
    for (let c = 0; c < 3; c++) {
      lut[q * 3 + c] = Math.round(rgb[i][c] + (rgb[i + 1][c] - rgb[i][c]) * f);
    }
  }
  return lut;
}

const LUT = buildLut();

const GUIDE_LINES_HZ = [1900, 2100];

export function SourceBandSpectrogram({
  sourceId,
  width = 760,
  height = 160,
  fmin = 1500,
  fmax = 2500,
}: {
  sourceId: number;
  width?: number;
  height?: number;
  fmin?: number;
  fmax?: number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [spec, setSpec] = useState<BandSpectrogram | null>(null);
  const [onsets, setOnsets] = useState<BeepOnsets | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setSpec(null);
    setOnsets(null);
    setFailed(false);
    Promise.all([
      getSourceBandSpectrogram(sourceId, fmin, fmax),
      getSourceBeepOnsets(sourceId),
    ])
      .then(([s, o]) => {
        if (cancelled) return;
        setSpec(s);
        setOnsets(o);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [sourceId, fmin, fmax]);

  useEffect(() => {
    if (!spec || !canvasRef.current || spec.cols === 0) return;
    const bin = atob(spec.data);
    const { freq_bins: rows, cols } = spec;
    const canvas = canvasRef.current;
    canvas.width = cols;
    canvas.height = rows;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const img = ctx.createImageData(cols, rows);
    for (let y = 0; y < rows; y++) {
      const srcRow = rows - 1 - y; // 행 0=fmin → 화면 아래쪽
      for (let x = 0; x < cols; x++) {
        const q = Math.min(255, bin.charCodeAt(srcRow * cols + x));
        const o = (y * cols + x) * 4;
        img.data[o] = LUT[q * 3];
        img.data[o + 1] = LUT[q * 3 + 1];
        img.data[o + 2] = LUT[q * 3 + 2];
        img.data[o + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }, [spec]);

  if (failed) {
    return <span className="text-xs text-content-subtle">비프 대역 분석 없음</span>;
  }
  if (spec === null || onsets === null) {
    return (
      <div
        className="animate-pulse rounded bg-surface-muted"
        style={{ width, height }}
        aria-hidden
      />
    );
  }

  const hzToY = (hz: number) => {
    const ratio = (hz - spec.fmin) / (spec.fmax - spec.fmin);
    return height * (1 - ratio); // 위=고음
  };
  const secToX = (sec: number) => (sec / spec.duration_sec) * width;

  // GT(검증) 판정: 오프셋 표준편차가 0.1초 이내면 규칙적 — 검출이 맞았다는 신호.
  const consistent = onsets.offset_stddev_sec <= 0.1 && onsets.count === 10;

  return (
    <div className="flex flex-col gap-2">
      <div className="relative" style={{ width, height }}>
        <canvas
          ref={canvasRef}
          role="img"
          aria-label={`비프 대역(${Math.round(spec.fmin)}~${Math.round(spec.fmax)}Hz) 스펙트로그램`}
          title={`비프 대역 · ${spec.duration_sec.toFixed(1)}초 · ${Math.round(spec.fmin)}~${Math.round(spec.fmax)}Hz · top_db ${spec.top_db}`}
          className="rounded border border-border"
          style={{ width, height, imageRendering: "auto" }}
        />
        {/* 1900/2100Hz 가이드라인 */}
        <div className="pointer-events-none absolute inset-0">
          {GUIDE_LINES_HZ.map((hz) => (
            <div
              key={hz}
              className="absolute left-0 right-0 border-t border-dashed border-white/40"
              style={{ top: hzToY(hz) }}
            />
          ))}
          {/* 검출된 onset — 기존 파형의 ▲(status.warn, 주황)와 구분되는
              status.error(적갈)로 세로선을 그린다. 토큰만 사용(CLAUDE.md §5). */}
          {onsets.onsets_sec.map((t, i) => (
            <div
              key={i}
              className="absolute top-0 bottom-0 w-px bg-status-error/70"
              style={{ left: secToX(t) }}
            />
          ))}
        </div>
      </div>

      <div className="flex justify-between text-xs text-content-subtle">
        <span>0초</span>
        <span>1900Hz / 2100Hz 점선</span>
        <span>{spec.duration_sec.toFixed(0)}초</span>
      </div>

      <div className="rounded border border-border bg-surface-muted p-2 text-xs">
        <div className={consistent ? "text-status-ok" : "text-status-warn"}>
          검출 {onsets.count}개 (기대 10개) ·{" "}
          {consistent ? "규칙적 — 검출 정상으로 보임" : "불규칙 — 임계값/대역폭 조정 필요"}
        </div>
        <div className="mt-1 tabular-nums text-content-subtle">
          오프셋(초%10): [{onsets.offsets_sec.map((v) => v.toFixed(2)).join(", ")}]
        </div>
        <div className="mt-1 tabular-nums text-content-subtle">
          오프셋 중앙값 {onsets.offset_median_sec?.toFixed(3) ?? "—"}초 · 표준편차{" "}
          {onsets.offset_stddev_sec.toFixed(3)}초
        </div>
        <div className="mt-1 tabular-nums text-content-subtle">
          간격: [{onsets.gaps_sec.map((v) => v.toFixed(2)).join(", ")}]
        </div>
      </div>
    </div>
  );
}
