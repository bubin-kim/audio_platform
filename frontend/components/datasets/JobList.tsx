import { Badge } from "@/components/ui/Badge";
import { formatDateTime } from "@/lib/format";
import type { Job } from "@/lib/types";
import { qualityCheckOf } from "@/components/datasets/QualityWarning";

/** Job.params.quality_check.sources[].filename들을 이어붙인다 — 어느 원본을
 * 커팅한 Job인지 이력에서 바로 알 수 있어야 한다 (여러 원본 한 Job에서
 * 처리된 경우 "A.wav 외 2개"로 축약). */
function sourceFilenamesOf(job: Job): string {
  const qc = qualityCheckOf(job);
  const names = qc?.sources.map((s) => s.filename) ?? [];
  if (names.length === 0) return "—";
  if (names.length === 1) return names[0];
  return `${names[0]} 외 ${names.length - 1}개`;
}

export function JobList({ jobs, total }: { jobs: Job[]; total: number }) {
  if (jobs.length === 0) {
    return <p className="text-sm text-content-muted">아직 실행된 Job이 없습니다.</p>;
  }

  return (
    <>
      {total > jobs.length && (
        <p className="mb-2 text-xs text-content-subtle">
          최근 {jobs.length}개 표시 중 — 전체 {total}개
        </p>
      )}
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-content-subtle">
            <th className="pb-2 font-normal">종류</th>
            <th className="pb-2 font-normal">원본 파일</th>
            <th className="pb-2 font-normal">상태</th>
            <th className="pb-2 font-normal">진행</th>
            <th className="pb-2 font-normal">시작</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {jobs.map((j) => (
            <tr key={j.id}>
              <td className="py-2 text-content">{j.type}</td>
              <td className="py-2 text-content" title={sourceFilenamesOf(j)}>
                {sourceFilenamesOf(j)}
              </td>
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
    </>
  );
}
