import type { Job, QualityCheck } from "@/lib/types";

/** Job.params에서 품질 검사 결과를 꺼낸다 (없으면 null — 기대치 미설정 프로젝트). */
export function qualityCheckOf(job: Job): QualityCheck | null {
  const qc = job.params?.quality_check as QualityCheck | undefined;
  return qc ?? null;
}

/**
 * 커팅 품질 경고 (docs/14) — 기대 조각 수와 다르면 재녹음 검토 안내.
 * 정상(ok)이거나 검사 미수행이면 아무것도 렌더링하지 않는다.
 */
export function QualityWarning({ job }: { job: Job }) {
  const qc = qualityCheckOf(job);
  if (!qc || qc.ok) return null;

  const bad = qc.sources.filter((s) => s.status !== "ok");
  return (
    <div className="mt-2 rounded-md border border-status-warn bg-surface-muted px-3 py-2 text-sm">
      <p className="font-medium text-status-warn">
        ⚠️ 조각 수가 기대와 다릅니다 — 재녹음이 필요할 수 있습니다
      </p>
      <ul className="mt-1 text-content-muted">
        {bad.map((s) => (
          <li key={s.source_file_id}>
            {s.filename}: {s.actual}/{s.expected}조각 (
            {s.status === "shortfall" ? "부족" : "초과 — 잡음 유입 가능성"})
          </li>
        ))}
      </ul>
    </div>
  );
}
