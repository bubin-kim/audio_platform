"use client";

import { useEffect, useState } from "react";

import { SourceBandSpectrogram } from "@/components/datasets/SourceBandSpectrogram";
import { Spectrogram } from "@/components/datasets/Spectrogram";
import { SourceWaveform } from "@/components/datasets/SourceWaveform";
import { Card } from "@/components/ui/Card";
import { listDatasetSources } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import type { SourceRead, SpectrogramMode } from "@/lib/types";

/** 기존 두 스펙트로그램 모드에 신규 "비프 대역 분석" 탭을 더한 뷰 선택.
 * SpectrogramMode 자체는 건드리지 않는다(기존 컴포넌트 계약 보존) — 이 파일
 * 안에서만 쓰는 뷰 선택용 타입을 하나 더 둔다. */
type SourceView = SpectrogramMode | "band_beep";

/**
 * 원본 파일 섹션 (docs/16) — 파일명·업로더·길이 + 행 펼치면 통 음원 스펙트로그램.
 * 스펙트로그램은 펼칠 때만 fetch(지연 로드) — 긴 원본 계산 비용을 아낀다.
 */
export function SourceList({ datasetId }: { datasetId: number }) {
  const [sources, setSources] = useState<SourceRead[] | null>(null);
  const [openIds, setOpenIds] = useState<Set<number>>(new Set());

  useEffect(() => {
    let cancelled = false;
    listDatasetSources(datasetId)
      .then((p) => !cancelled && setSources(p.items))
      .catch(() => !cancelled && setSources([]));
    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  if (sources === null || sources.length === 0) return null;

  function toggle(id: number) {
    setOpenIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <Card>
      <p className="text-sm font-medium text-content">원본 파일</p>
      <table className="mt-3 w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-content-subtle">
            <th className="py-1 font-normal">파일명</th>
            <th className="py-1 font-normal">업로더</th>
            <th className="py-1 font-normal">길이</th>
            <th className="py-1 font-normal">포맷</th>
            <th className="py-1 font-normal" aria-hidden />
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {sources.map((s) => (
            <SourceRow
              key={s.id}
              source={s}
              open={openIds.has(s.id)}
              onToggle={() => toggle(s.id)}
            />
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function SourceRow({
  source,
  open,
  onToggle,
}: {
  source: SourceRead;
  open: boolean;
  onToggle: () => void;
}) {
  const [view, setView] = useState<SourceView>("absolute");

  return (
    <>
      <tr>
        <td className="py-2 text-content">{source.filename}</td>
        <td className="py-2 text-content-muted">{source.uploaded_by ?? "—"}</td>
        <td className="py-2 text-content-muted">
          {source.duration_sec !== null ? formatDuration(source.duration_sec) : "—"}
        </td>
        <td className="py-2 text-content-subtle">{source.format ?? "—"}</td>
        <td className="py-2 text-right">
          <button
            type="button"
            onClick={onToggle}
            className="text-xs text-accent hover:underline"
            aria-expanded={open}
          >
            {open ? "시각화 접기" : "파형·스펙트로그램 보기"}
          </button>
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={5} className="pb-3">
            <div className="mb-2 flex items-center gap-2 text-xs">
              <span className="text-content-subtle">보기:</span>
              {(
                [
                  ["absolute", "실제 크기"],
                  ["contrast", "배경 제거 (묻힌 소리 찾기)"],
                  ["band_beep", "비프 대역 (1.5~2.5k)"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setView(value)}
                  className={`rounded-full border px-2.5 py-1 transition-colors ${
                    view === value
                      ? "border-accent bg-accent-soft text-accent"
                      : "border-border bg-surface-card text-content-muted hover:bg-surface-muted"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="mb-3">
              <p className="mb-1 text-xs text-content-subtle">
                {view === "band_beep"
                  ? "대역통과 파형 — 1.8~2.2kHz만 남긴 소리 크기(자동 확대). ▲는 검출된 비프음 위치"
                  : "전체 파형 — 세로=진폭, 가로=시간. ▲는 대역통과 검출기가 찾은 비프음 위치(비프 대역 탭의 빨간 세로선과 같은 지점)"}
              </p>
              {/* 4채널(앰비소닉) 원본을 화면에는 한 장으로 합쳐 그린다 —
                  저장된 파일은 4채널 그대로라는 점을 명시(오해 방지, docs/18 §5). */}
              <p className="mb-1 text-xs text-content-subtle">
                ※ 원본은 4채널(앰비소닉)이며, 화면 표시를 위해 합쳐서 그립니다.
                저장된 파일과 잘린 조각은 4채널 24bit 그대로입니다.
              </p>
              {/* band 모드에서는 SourceWaveform이 **자체 축**(대역 표기 +
                  진폭 눈금)을 HZ_AXIS_PX 폭으로 그린다 — 여기서 또
                  들여쓰면 두 번 밀려 스펙트로그램과 어긋난다. */}
              <SourceWaveform
                sourceId={source.id}
                width={760}
                height={120}
                band={view === "band_beep"}
              />
            </div>
            {view === "band_beep" ? (
              <>
                <SourceBandSpectrogram sourceId={source.id} width={760} height={160} />
                <p className="mt-1 text-xs text-content-subtle">
                  세로=주파수(1500~2500Hz만 확대, 위가 고음) · 가로=시간 ·
                  점선=1900/2100Hz · 빨간 세로선=대역통과 검출기가 찾은 비프음
                  onset(신규, 표시 전용 — 라벨로 저장되지 않습니다).
                </p>
              </>
            ) : (
              <>
                <Spectrogram
                  kind="source"
                  id={source.id}
                  width={760}
                  height={140}
                  mode={view}
                  showAxis
                />
                <p className="mt-1 text-xs text-content-subtle">
                  세로=주파수(아래가 저음) · 가로=시간 · 밝을수록 큰 소리.
                  {view === "contrast" &&
                    " 각 주파수의 평소 수준을 뺀 값이라, 환경음에 묻힌 소리도 밝게 드러납니다."}
                </p>
              </>
            )}
          </td>
        </tr>
      )}
    </>
  );
}
