import { DistributionBar } from "@/components/dashboard/DistributionBar";
import { ProgressStat } from "@/components/dashboard/ProgressStat";
import { ProjectStatsTable } from "@/components/dashboard/ProjectStatsTable";
import { RecentUploads } from "@/components/dashboard/RecentUploads";
import { StatCard } from "@/components/dashboard/StatCard";
import { Header } from "@/components/layout/Header";
import { getStats } from "@/lib/api";
import { formatBytes, formatDuration } from "@/lib/format";

export default async function DashboardPage() {
  const stats = await getStats();

  return (
    <>
      <Header title="대시보드" />
      <main className="mx-auto max-w-6xl px-8 py-8">
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard
            label="총 세그먼트 수"
            value={String(stats.total_segments)}
            tone="bg-chip-1"
          />
          <StatCard
            label="총 녹음 시간"
            value={formatDuration(stats.total_duration_sec)}
            tone="bg-chip-2"
          />
          <StatCard
            label="저장 용량"
            value={formatBytes(stats.total_size_bytes)}
            tone="bg-chip-3"
          />
          <StatCard
            label="평균 길이"
            value={formatDuration(stats.avg_duration_sec)}
            tone="bg-chip-4"
          />
        </div>

        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          <ProgressStat
            title="업로드 진행률"
            current={formatDuration(stats.upload_progress.current_sec)}
            target={
              stats.upload_progress.target_sec !== null
                ? formatDuration(stats.upload_progress.target_sec)
                : null
            }
            ratio={stats.upload_progress.ratio}
          />
          <ProgressStat
            title="라벨링 진행률"
            current={`${stats.labeling_progress.labeled} / ${stats.labeling_progress.total}`}
            target={null}
            ratio={stats.labeling_progress.ratio}
          />
        </div>

        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          <DistributionBar
            title="Sample Rate 분포"
            distribution={stats.sample_rate_distribution}
          />
          <DistributionBar
            title="파일 형식 통계"
            distribution={stats.format_distribution}
          />
        </div>

        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          {stats.per_project && (
            <ProjectStatsTable projects={stats.per_project} />
          )}
          <RecentUploads uploads={stats.recent_uploads} />
        </div>
      </main>
    </>
  );
}
