"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { LabelValuesForm } from "@/components/datasets/LabelValuesForm";
import { SegmentWaveform } from "@/components/datasets/SegmentWaveform";
import { Button } from "@/components/ui/Button";
import { deleteSegment, segmentAudioUrl, updateSegmentLabels } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import type { LabelFieldSchema, Segment } from "@/lib/types";

export function SegmentTable({
  segments,
  total,
  labelSchema,
}: {
  segments: Segment[];
  total: number;
  labelSchema: LabelFieldSchema[];
}) {
  const router = useRouter();
  const [playingId, setPlayingId] = useState<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  // 인라인 라벨 편집 — 한 번에 한 행만 (개별 예외 보정, 06 §8)
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState<Record<string, unknown>>({});
  const [rowError, setRowError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // 페이지를 떠날 때 재생 중이던 오디오를 정지한다.
  useEffect(() => {
    return () => audioRef.current?.pause();
  }, []);

  function togglePlay(segmentId: number) {
    const audio = audioRef.current;
    if (!audio) return;
    if (playingId === segmentId) {
      audio.pause();
      setPlayingId(null);
      return;
    }
    audio.src = segmentAudioUrl(segmentId);
    audio
      .play()
      .then(() => setPlayingId(segmentId))
      .catch(() => setPlayingId(null));
  }

  function startEdit(s: Segment) {
    // 기존 라벨 중 스키마에 있는 키만, 빈 값은 빼고 초기화한다.
    const initial: Record<string, unknown> = {};
    for (const f of labelSchema) {
      const v = s.labels[f.key];
      if (v !== undefined && v !== null && v !== "") initial[f.key] = v;
    }
    setDraft(initial);
    setRowError(null);
    setEditingId(s.id);
  }

  async function saveEdit(segmentId: number) {
    setBusy(true);
    setRowError(null);
    try {
      // 빈 문자열은 "값 지정 안 함"으로 보고 보내지 않는다 (enum "" 검증 회피).
      const payload = Object.fromEntries(
        Object.entries(draft).filter(([, v]) => v !== "" && v !== undefined),
      );
      await updateSegmentLabels(segmentId, payload);
      setEditingId(null);
      router.refresh();
    } catch (err) {
      setRowError(err instanceof Error ? err.message : "알 수 없는 오류");
    } finally {
      setBusy(false);
    }
  }

  async function removeSegment(s: Segment) {
    if (!window.confirm(`세그먼트 ${s.filename}을(를) 삭제할까요? (파일 포함, 되돌릴 수 없음)`)) {
      return;
    }
    setBusy(true);
    try {
      await deleteSegment(s.id);
      if (playingId === s.id) {
        audioRef.current?.pause();
        setPlayingId(null);
      }
      router.refresh();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "삭제 실패");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <audio ref={audioRef} onEnded={() => setPlayingId(null)} />
      <p className="mb-2 text-sm text-content-subtle">
        총 {total}개 중 {segments.length}개 표시
      </p>
      {segments.length === 0 ? (
        <p className="text-sm text-content-muted">
          아직 세그먼트가 없습니다. 위에서 커팅을 시작해 보세요.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-content-subtle">
                <th className="pb-2 pr-2 font-normal">재생</th>
                <th className="pb-2 pr-4 font-normal">파형</th>
                <th className="pb-2 pr-4 font-normal">파일명</th>
                <th className="pb-2 pr-4 font-normal">길이</th>
                <th className="pb-2 pr-4 font-normal">Sample Rate</th>
                <th className="pb-2 pr-4 font-normal">라벨</th>
                <th className="pb-2 pr-4 font-normal">라벨링</th>
                <th className="pb-2 font-normal">작업</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {segments.map((s) => (
                <tr key={s.id} className="align-top">
                  <td className="py-2 pr-2">
                    <button
                      type="button"
                      onClick={() => togglePlay(s.id)}
                      aria-label={playingId === s.id ? "정지" : "재생"}
                      className={`flex h-7 w-7 items-center justify-center rounded-full border text-xs transition-colors ${
                        playingId === s.id
                          ? "border-accent bg-accent-soft text-accent"
                          : "border-border text-content-muted hover:bg-surface-muted"
                      }`}
                    >
                      {playingId === s.id ? "■" : "▶"}
                    </button>
                  </td>
                  <td className="py-2 pr-4">
                    <SegmentWaveform segmentId={s.id} />
                  </td>
                  <td className="py-2 pr-4 text-content">{s.filename}</td>
                  <td className="py-2 pr-4 text-content-muted">
                    {formatDuration(s.duration_sec)}
                  </td>
                  <td className="py-2 pr-4 text-content-muted">
                    {s.sample_rate}Hz
                  </td>
                  <td className="py-2 pr-4 text-content-muted">
                    {editingId === s.id ? (
                      <div className="min-w-56 max-w-72">
                        <LabelValuesForm
                          schema={labelSchema}
                          values={draft}
                          onChange={setDraft}
                        />
                        {rowError && (
                          <p className="mt-1 text-xs text-status-error">{rowError}</p>
                        )}
                        <div className="mt-2 flex gap-2">
                          <Button
                            type="button"
                            disabled={busy}
                            onClick={() => saveEdit(s.id)}
                          >
                            {busy ? "저장 중..." : "저장"}
                          </Button>
                          <Button
                            type="button"
                            variant="secondary"
                            onClick={() => setEditingId(null)}
                          >
                            취소
                          </Button>
                        </div>
                      </div>
                    ) : (
                      Object.entries(s.labels)
                        .filter(([, v]) => v !== "" && v !== null)
                        .map(([k, v]) => `${k}=${v}`)
                        .join(", ") || "—"
                    )}
                  </td>
                  <td className="py-2 pr-4 text-content-muted">
                    {s.is_labeled ? "✓" : "—"}
                  </td>
                  <td className="py-2">
                    {editingId !== s.id && (
                      <div className="flex gap-2 whitespace-nowrap">
                        {labelSchema.length > 0 && (
                          <button
                            type="button"
                            onClick={() => startEdit(s)}
                            className="text-xs text-accent hover:underline"
                          >
                            라벨 수정
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => removeSegment(s)}
                          disabled={busy}
                          className="text-xs text-status-error hover:underline"
                        >
                          삭제
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
