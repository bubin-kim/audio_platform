import Link from "next/link";

import { ExportPanel } from "@/components/datasets/ExportPanel";
import { JobList } from "@/components/datasets/JobList";
import { ProcessingPanel } from "@/components/datasets/ProcessingPanel";
import { SegmentTable } from "@/components/datasets/SegmentTable";
import { Header } from "@/components/layout/Header";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { DangerDeleteCard } from "@/components/ui/DangerDeleteCard";
import { getDataset, getProject, listJobs, listSegments } from "@/lib/api";

export default async function DatasetDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const datasetId = Number(id);
  const dataset = await getDataset(datasetId);
  const [project, jobsPage, segmentsPage] = await Promise.all([
    getProject(dataset.project_id),
    listJobs(datasetId, { limit: 20 }),
    listSegments(datasetId, { limit: 50 }),
  ]);

  return (
    <>
      <Header title={dataset.name} />
      <main className="mx-auto max-w-6xl px-8 py-8">
        <Card>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-content-subtle">{dataset.version}</p>
              <Link
                href={`/projects/${project.id}`}
                className="mt-1 inline-block text-lg font-medium text-content hover:underline"
              >
                {project.name}
              </Link>
            </div>
            <Badge status={dataset.status} />
          </div>
        </Card>

        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          <Card>
            <p className="mb-3 text-sm font-medium text-content">커팅</p>
            <ProcessingPanel
              datasetId={datasetId}
              labelSchema={project.label_schema}
            />
          </Card>
          <Card>
            <p className="mb-3 text-sm font-medium text-content">
              CSV 내보내기
            </p>
            <ExportPanel datasetId={datasetId} />
          </Card>
        </div>

        <Card className="mt-4">
          <p className="mb-3 text-sm font-medium text-content">Job 이력</p>
          <JobList jobs={jobsPage.items} />
        </Card>

        <Card className="mt-4">
          <p className="mb-3 text-sm font-medium text-content">세그먼트</p>
          <SegmentTable
            segments={segmentsPage.items}
            total={segmentsPage.total}
            labelSchema={project.label_schema}
          />
        </Card>

        <div className="mt-6">
          <DangerDeleteCard
            kind="dataset"
            id={datasetId}
            name={dataset.name}
            redirectTo={`/projects/${project.id}`}
          />
        </div>
      </main>
    </>
  );
}
