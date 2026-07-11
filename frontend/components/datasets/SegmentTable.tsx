"use client";

import { useEffect, useRef, useState } from "react";

import { SegmentWaveform } from "@/components/datasets/SegmentWaveform";
import { segmentAudioUrl } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import type { Segment } from "@/lib/types";

export function SegmentTable({
  segments,
  total,
}: {
  segments: Segment[];
  total: number;
}) {
  const [playingId, setPlayingId] = useState<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

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
                <th className="pb-2 font-normal">라벨링</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {segments.map((s) => (
                <tr key={s.id}>
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
                    {Object.entries(s.labels)
                      .map(([k, v]) => `${k}=${v}`)
                      .join(", ") || "—"}
                  </td>
                  <td className="py-2 text-content-muted">
                    {s.is_labeled ? "✓" : "—"}
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
