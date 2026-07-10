"use client";

import { useEffect, useState } from "react";

import { getJob } from "@/lib/api";
import type { Job } from "@/lib/types";

const TERMINAL: Job["status"][] = ["done", "failed"];

/** jobId가 주어지면 done/failed가 될 때까지 폴링한다. Processing·Export 패널이 공유. */
export function useJobPolling(jobId: number | null, intervalMs = 2000): Job | null {
  const [job, setJob] = useState<Job | null>(null);

  useEffect(() => {
    if (jobId === null) {
      setJob(null);
      return;
    }
    let cancelled = false;
    let timer: ReturnType<typeof setInterval>;

    async function tick() {
      try {
        const latest = await getJob(jobId as number);
        if (cancelled) return;
        setJob(latest);
        if (TERMINAL.includes(latest.status)) {
          clearInterval(timer);
        }
      } catch {
        // 폴링 중 일시적 오류는 무시하고 다음 tick에서 재시도한다.
      }
    }

    tick();
    timer = setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [jobId, intervalMs]);

  return job;
}
