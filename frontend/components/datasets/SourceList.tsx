"use client";

import { useEffect, useState } from "react";

import { Spectrogram } from "@/components/datasets/Spectrogram";
import { SourceWaveform } from "@/components/datasets/SourceWaveform";
import { Card } from "@/components/ui/Card";
import { listDatasetSources } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import type { SourceRead, SpectrogramMode } from "@/lib/types";

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
  const [mode, setMode] = useState<SpectrogramMode>("absolute");

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
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setMode(value)}
                  className={`rounded-full border px-2.5 py-1 transition-colors ${
                    mode === value
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
                전체 파형 — 세로=진폭, 가로=시간. ▲는 평균보다 크게 튄 지점(후보)
              </p>
              <SourceWaveform sourceId={source.id} width={760} height={120} />
            </div>
            <Spectrogram
              kind="source"
              id={source.id}
              width={760}
              height={140}
              mode={mode}
              showAxis
            />
            <p className="mt-1 text-xs text-content-subtle">
              세로=주파수(아래가 저음) · 가로=시간 · 밝을수록 큰 소리.
              {mode === "contrast" &&
                " 각 주파수의 평소 수준을 뺀 값이라, 환경음에 묻힌 소리도 밝게 드러납니다."}
            </p>
          </td>
        </tr>
      )}
    </>
  );
}
