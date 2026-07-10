"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { downloadExportUrl, startExport } from "@/lib/api";
import { useJobPolling } from "@/lib/useJobPolling";

export function ExportPanel({ datasetId }: { datasetId: number }) {
  const router = useRouter();
  const [jobId, setJobId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const job = useJobPolling(jobId);

  useEffect(() => {
    if (job?.status === "done") router.refresh();
  }, [job?.status, router]);

  const inFlight = starting || job?.status === "queued" || job?.status === "running";

  async function handleStart() {
    setStarting(true);
    setError(null);
    try {
      const created = await startExport(datasetId);
      setJobId(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "알 수 없는 오류");
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <Button variant="secondary" onClick={handleStart} disabled={inFlight}>
        {inFlight ? "내보내는 중..." : "CSV 내보내기"}
      </Button>
      {error && <p className="text-sm text-status-error">{error}</p>}
      {job && (
        <div className="flex items-center justify-between rounded-md border border-border p-3">
          <Badge status={job.status} />
          {job.status === "done" ? (
            <a
              href={downloadExportUrl(datasetId)}
              className="text-sm text-accent hover:underline"
            >
              metadata.csv 다운로드 →
            </a>
          ) : job.error_msg ? (
            <span className="text-sm text-status-error">{job.error_msg}</span>
          ) : (
            <span className="text-xs text-content-subtle">진행 중...</span>
          )}
        </div>
      )}
    </div>
  );
}
