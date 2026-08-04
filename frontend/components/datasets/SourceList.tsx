"use client";

import { useEffect, useState } from "react";

import { Spectrogram } from "@/components/datasets/Spectrogram";
import { Card } from "@/components/ui/Card";
import { listDatasetSources } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import type { SourceRead } from "@/lib/types";

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
            {open ? "스펙트로그램 접기" : "스펙트로그램 보기"}
          </button>
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={5} className="pb-3">
            <Spectrogram kind="source" id={source.id} width={760} height={140} />
          </td>
        </tr>
      )}
    </>
  );
}
