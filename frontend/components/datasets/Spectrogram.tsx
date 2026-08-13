"use client";

import { useEffect, useRef, useState } from "react";

import { getSegmentSpectrogram, getSourceSpectrogram } from "@/lib/api";
import type {
  Spectrogram as SpectrogramData,
  SpectrogramMode,
} from "@/lib/types";
import { useLazyVisible } from "@/lib/useLazyVisible";
import { formatHz, hzToRatio, pickFrequencyTicks } from "@/lib/mel";
import config from "@/tailwind.config";

/**
 * 멜 스펙트로그램 캔버스 (docs/16). 세로=주파수(멜, 아래=저음), 가로=시간.
 * 색은 viridis 램프 — 조용하면 어두운 보라, 소리가 강하면 밝은 노랑이라
 * 환경음에 묻힌 이벤트도 밝은 점/줄무늬로 눈에 띈다.
 * dB는 절대 스케일(백엔드 양자화 그대로)이라 파일 간 밝기 비교가 가능하다.
 * 캔버스는 CSS 클래스를 못 쓰므로 tailwind 토큰(spectro)을 직접 import한다.
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

/** 0~100 → RGB 룩업 테이블 (램프 4스톱 구간별 선형 보간). */
function buildLut(): Uint8Array {
  const rgb = STOPS.map(hexToRgb);
  const lut = new Uint8Array(101 * 3);
  for (let q = 0; q <= 100; q++) {
    const t = (q / 100) * (rgb.length - 1);
    const i = Math.min(Math.floor(t), rgb.length - 2);
    const f = t - i;
    for (let c = 0; c < 3; c++) {
      lut[q * 3 + c] = Math.round(rgb[i][c] + (rgb[i + 1][c] - rgb[i][c]) * f);
    }
  }
  return lut;
}

const LUT = buildLut();

export function Spectrogram({
  kind,
  id,
  width = 120,
  height = 28,
  mode = "absolute",
  showAxis = false,
}: {
  kind: "segment" | "source";
  id: number;
  width?: number;
  height?: number;
  mode?: SpectrogramMode;
  /** 주파수 눈금(Hz) 표시 — 큰 화면에서만. 미니 위젯은 공간이 없어 끈다. */
  showAxis?: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [wrapRef, visible] = useLazyVisible<HTMLDivElement>();
  const [spec, setSpec] = useState<SpectrogramData | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    const fetcher =
      kind === "segment" ? getSegmentSpectrogram : getSourceSpectrogram;
    setSpec(null);
    setFailed(false);
    fetcher(id, mode)
      .then((s) => !cancelled && setSpec(s))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [kind, id, visible, mode]);

  useEffect(() => {
    if (!spec || !canvasRef.current || spec.cols === 0) return;
    const bin = atob(spec.data);
    const { n_mels: rows, cols } = spec;
    // 원본 해상도(cols×rows)로 그린 뒤 CSS로 늘린다 (픽셀 보간은 브라우저가)
    const canvas = canvasRef.current;
    canvas.width = cols;
    canvas.height = rows;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const img = ctx.createImageData(cols, rows);
    for (let y = 0; y < rows; y++) {
      const srcRow = rows - 1 - y; // 행 0=최저음 → 화면 아래쪽
      for (let x = 0; x < cols; x++) {
        const q = Math.min(100, bin.charCodeAt(srcRow * cols + x));
        const o = (y * cols + x) * 4;
        img.data[o] = LUT[q * 3];
        img.data[o + 1] = LUT[q * 3 + 1];
        img.data[o + 2] = LUT[q * 3 + 2];
        img.data[o + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }, [spec]);

  if (!visible) {
    return <div ref={wrapRef} style={{ width, height }} aria-hidden />;
  }
  if (failed) {
    return <span className="text-xs text-content-subtle">스펙트로그램 없음</span>;
  }
  if (spec === null) {
    return (
      <div
        className="animate-pulse rounded bg-surface-muted"
        style={{ width, height }}
        aria-hidden
      />
    );
  }

  const canvas = (
    <canvas
      ref={canvasRef}
      role="img"
      aria-label="멜 스펙트로그램 (아래=저음)"
      title={`멜 스펙트로그램 · ${spec.duration_sec.toFixed(1)}초 · ~${Math.round(spec.fmax / 1000)}kHz(멜) · ${spec.db_floor}~${spec.db_ceil}dB (밝을수록 큰 소리)`}
      className="rounded border border-border"
      style={{ width, height, imageRendering: "auto" }}
    />
  );

  if (!showAxis) return canvas;

  // 눈금은 멜 스케일 위치에 찍는다 — 선형으로 찍으면 저음이 크게 어긋난다
  // (2kHz는 높이의 8%가 아니라 41% 지점).
  const ticks = pickFrequencyTicks(spec.fmax);

  // 라벨과 눈금선은 **같은 높이 기준**(캔버스 height)에서 배치해야 어긋나지 않는다.
  // 컨테이너에 items-stretch를 주면 라벨 영역이 캔버스보다 커져 20px씩 밀린다(실측).
  return (
    <div className="flex items-start gap-1">
      <div
        className="relative w-11 shrink-0 text-right text-[10px] leading-none text-content-subtle"
        style={{ height }}
        aria-hidden
      >
        {ticks.map((hz) => (
          <span
            key={hz}
            className="absolute right-0 tabular-nums"
            style={{
              bottom: `${hzToRatio(hz, spec.fmax, spec.n_mels) * 100}%`,
              transform: "translateY(50%)",
            }}
          >
            {formatHz(hz)}
          </span>
        ))}
      </div>
      <div className="relative" style={{ width, height }}>
        {canvas}
        {/* 눈금선 — 캔버스 위에 옅게 (recessive) */}
        <div className="pointer-events-none absolute inset-0">
          {ticks.map((hz) => (
            <div
              key={hz}
              className="absolute left-0 right-0 border-t border-white/25"
              style={{ bottom: `${hzToRatio(hz, spec.fmax, spec.n_mels) * 100}%` }}
            />
          ))}
        </div>
      </div>
      <span
        className="shrink-0 text-[10px] leading-none text-content-subtle"
        style={{ marginTop: height - 6 }}
      >
        Hz
      </span>
    </div>
  );
}
