import { Badge } from "@/components/ui/Badge";
import { formatDateTime } from "@/lib/format";
import type { Job } from "@/lib/types";
import { qualityCheckOf } from "@/components/datasets/QualityWarning";

export function JobList({ jobs }: { jobs: Job[] }) {
  if (jobs.length === 0) {
    return <p className="text-sm text-content-muted">아직 실행된 Job이 없습니다.</p>;
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-content-subtle">
          <th className="pb-2 font-normal">종류</th>
          <th className="pb-2 font-normal">상태</th>
          <th className="pb-2 font-normal">진행</th>
          <th className="pb-2 font-normal">시작</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-border">
        {jobs.map((j) => (
          <tr key={j.id}>
            <td className="py-2 text-content">{j.type}</td>
            <td className="py-2">
              <Badge status={j.status} />
            </td>
            <td className="py-2 text-content-muted">
              {j.progress}
              {j.total_items !== null && ` / ${j.total_items}`}
              {qualityCheckOf(j)?.ok === false && (
                <span className="ml-1 text-status-warn" title="조각 수가 기대와 다름 — 재녹음 검토">
                  ⚠️
                </span>
              )}
            </td>
            <td className="py-2 text-content-subtle">
              {j.started_at ? formatDateTime(j.started_at) : "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
