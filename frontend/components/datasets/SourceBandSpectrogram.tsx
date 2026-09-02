"use client";

import { useEffect, useRef, useState } from "react";

import { getSourceBandSpectrogram, getSourceBeepOnsets } from "@/lib/api";
import { formatHz } from "@/lib/mel";
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

/** Hz 축(라벨 w-11=44px + gap-1=4px)이 차지하는 왼쪽 폭.
 * 이 컴포넌트의 시간 라벨과, 위에 함께 놓이는 파형(SourceList)의 들여쓰기가
 * **같은 값**을 써야 두 그림의 시간축이 세로로 맞는다. */
export const HZ_AXIS_PX = 48;

/** 크롭 대역에 찍을 Hz 눈금. 멜과 달리 **선형**이라 위치 계산이 단순하다.
 * 200Hz 간격으로 끊되, 대역이 좁으면 100Hz까지 촘촘하게 내려간다. */
function pickBandTicks(fmin: number, fmax: number): number[] {
  const span = fmax - fmin;
  const step = span <= 400 ? 100 : span <= 1200 ? 200 : 500;
  const ticks: number[] = [];
  for (let hz = Math.ceil(fmin / step) * step; hz <= fmax; hz += step) {
    ticks.push(hz);
  }
  return ticks;
}

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

  // 판정: 주기 모드는 주기 수만큼 항상 돌려주므로 개수보다 **위상 일관성**이
  // 중요하다. 오프셋 표준편차가 작으면 진짜 비프음을 따라간 것이고, 크면
  // 주기 위상을 못 찾아 엉뚱한 곳을 짚고 있다는 신호(실측: 정상 파일들은
  // 0.08~0.27초, 실패한 파일은 3.7초).
  const consistent = onsets.offset_stddev_sec <= 0.5;

  const ticks = pickBandTicks(spec.fmin, spec.fmax);

  return (
    <div className="flex flex-col gap-2">
      {/* 라벨과 눈금선은 같은 높이 기준(캔버스 height)에 배치한다 —
          items-stretch를 주면 라벨 영역이 캔버스보다 커져 어긋난다
          (기존 Spectrogram.tsx에서 실측된 함정, 같은 구조를 따른다). */}
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
                bottom: `${((hz - spec.fmin) / (spec.fmax - spec.fmin)) * 100}%`,
                transform: "translateY(50%)",
              }}
            >
              {formatHz(hz)}
            </span>
          ))}
        </div>
        <div className="relative" style={{ width, height }}>
          <canvas
            ref={canvasRef}
            role="img"
            aria-label={`비프 대역(${Math.round(spec.fmin)}~${Math.round(spec.fmax)}Hz) 스펙트로그램`}
            title={`비프 대역 · ${spec.duration_sec.toFixed(1)}초 · ${Math.round(spec.fmin)}~${Math.round(spec.fmax)}Hz · top_db ${spec.top_db}`}
            className="rounded border border-border"
            style={{ width, height, imageRendering: "auto" }}
          />
          <div className="pointer-events-none absolute inset-0">
            {/* Hz 눈금선 — 캔버스 위에 옅게 (recessive) */}
            {ticks.map((hz) => (
              <div
                key={hz}
                className="absolute left-0 right-0 border-t border-white/20"
                style={{
                  bottom: `${((hz - spec.fmin) / (spec.fmax - spec.fmin)) * 100}%`,
                }}
              />
            ))}
            {/* 1900/2100Hz 가이드라인 — 눈금선보다 진하게 (비프음 대역 표시) */}
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
        <span
          className="shrink-0 text-[10px] leading-none text-content-subtle"
          style={{ marginTop: height - 6 }}
        >
          Hz
        </span>
      </div>

      {/* 시간 라벨은 **캔버스와 같은 폭·같은 시작점**에 둔다.
          컨테이너 전체에 justify-between을 걸면 Hz 축(왼쪽 48px)과 "Hz"
          접미사(오른쪽)까지 포함해 퍼져서, 0초·100초가 캔버스 밖으로
          나간다(실측: 100초 라벨이 캔버스 오른쪽 끝보다 203px 바깥).
          그러면 위의 파형과 시간 눈금이 어긋나 보인다. */}
      <div className="flex" style={{ paddingLeft: HZ_AXIS_PX }}>
        <div
          className="flex justify-between text-xs text-content-subtle"
          style={{ width }}
        >
          <span>0초</span>
          <span>1900Hz / 2100Hz 점선 = 비프음 대역</span>
          <span>{spec.duration_sec.toFixed(0)}초</span>
        </div>
      </div>

      <div className="rounded border border-border bg-surface-muted p-2 text-xs">
        <div className={consistent ? "text-status-ok" : "text-status-warn"}>
          검출 {onsets.count}개 (기대 10개) · 위상 표준편차{" "}
          {onsets.offset_stddev_sec.toFixed(2)}초 ·{" "}
          {consistent
            ? "규칙적 — 검출 정상으로 보임"
            : "위상이 흔들림 — 이 파일은 사람이 직접 확인 필요"}
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
