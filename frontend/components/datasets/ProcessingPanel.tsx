"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { LabelValuesForm } from "@/components/datasets/LabelValuesForm";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { ApiRequestError, startProcessing } from "@/lib/api";
import type { LabelFieldSchema } from "@/lib/types";
import { useJobPolling } from "@/lib/useJobPolling";

export function ProcessingPanel({
  datasetId,
  labelSchema,
}: {
  datasetId: number;
  labelSchema: LabelFieldSchema[];
}) {
  const router = useRouter();
  const [labels, setLabels] = useState<Record<string, unknown>>({});
  const [jobId, setJobId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 409(기존 세그먼트 존재) 시 대체 재커팅 안내 (docs/10, docs/12 B3)
  const [conflictMsg, setConflictMsg] = useState<string | null>(null);
  const [inheritLabels, setInheritLabels] = useState(true);
  const [starting, setStarting] = useState(false);
  const job = useJobPolling(jobId);

  // 커팅이 끝나면 세그먼트 표·Job 이력이 최신 데이터를 보도록 서버 컴포넌트를 다시 읽는다.
  useEffect(() => {
    if (job?.status === "done") router.refresh();
  }, [job?.status, router]);

  const inFlight = starting || job?.status === "queued" || job?.status === "running";

  async function handleStart(replaceExisting = false) {
    setStarting(true);
    setError(null);
    setConflictMsg(null);
    try {
      const created = await startProcessing(datasetId, {
        common_labels: labels,
        ...(replaceExisting
          ? { replace_existing: true, inherit_labels: inheritLabels }
          : {}),
      });
      setJobId(created.id);
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 409) {
        // 이미 커팅된 원본 → 사용자가 명시적으로 대체를 선택해야 진행 (docs/10 §3)
        setConflictMsg(err.message);
      } else {
        setError(err instanceof Error ? err.message : "알 수 없는 오류");
      }
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <LabelValuesForm schema={labelSchema} values={labels} onChange={setLabels} />
      <Button onClick={() => handleStart()} disabled={inFlight}>
        {inFlight ? "커팅 진행 중..." : "커팅 시작"}
      </Button>
      {error && <p className="text-sm text-status-error">{error}</p>}
      {conflictMsg && (
        <div className="rounded-md border border-status-warn/40 bg-surface-muted p-3">
          <p className="text-sm text-content">{conflictMsg}</p>
          <label className="mt-2 flex items-center gap-2 text-xs text-content-muted">
            <input
              type="checkbox"
              checked={inheritLabels}
              onChange={(e) => setInheritLabels(e.target.checked)}
            />
            기존 라벨 자동 승계 (구간 겹침 매칭)
          </label>
          <div className="mt-2 flex gap-2">
            <Button type="button" disabled={inFlight} onClick={() => handleStart(true)}>
              기존 세그먼트 대체 재커팅
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => setConflictMsg(null)}
            >
              취소
            </Button>
          </div>
        </div>
      )}
      {job && (
        <div className="rounded-md border border-border p-3">
          <div className="flex items-center justify-between">
            <Badge status={job.status} />
            <span className="text-xs text-content-subtle">
              {job.progress}
              {job.total_items !== null && ` / ${job.total_items}`}
            </span>
          </div>
          <div className="mt-2">
            <ProgressBar
              ratio={
                job.total_items
                  ? job.progress / job.total_items
                  : job.status === "done"
                    ? 1
                    : null
              }
            />
          </div>
          {job.error_msg && (
            <p className="mt-2 text-sm text-status-error">{job.error_msg}</p>
          )}
        </div>
      )}
    </div>
  );
}
