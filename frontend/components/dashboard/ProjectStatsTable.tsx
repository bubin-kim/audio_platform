import Link from "next/link";

import { Card } from "@/components/ui/Card";
import { formatDuration } from "@/lib/format";
import type { ProjectStats } from "@/lib/types";

export function ProjectStatsTable({ projects }: { projects: ProjectStats[] }) {
  return (
    <Card>
      <p className="text-sm text-content-subtle">프로젝트별 현황</p>
      {projects.length === 0 ? (
        <p className="mt-3 text-sm text-content-muted">아직 프로젝트가 없습니다.</p>
      ) : (
        <table className="mt-3 w-full text-sm">
          <thead>
            <tr className="text-left text-content-subtle">
              <th className="pb-2 font-normal">프로젝트</th>
              <th className="pb-2 font-normal">세그먼트 수</th>
              <th className="pb-2 font-normal">총 녹음 시간</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {projects.map((p) => (
              <tr key={p.project_id}>
                <td className="py-2">
                  <Link
                    href={`/projects/${p.project_id}`}
                    className="text-accent hover:underline"
                  >
                    {p.name}
                  </Link>
                </td>
                <td className="py-2 text-content">{p.segment_count}</td>
                <td className="py-2 text-content">
                  {formatDuration(p.duration_sec)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}
