import Link from "next/link";

import { DatasetCreateForm } from "@/components/datasets/DatasetCreateForm";
import { Header } from "@/components/layout/Header";
import { ProjectSettingsCard } from "@/components/projects/ProjectSettingsCard";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { DangerDeleteCard } from "@/components/ui/DangerDeleteCard";
import { getProject, listDatasets } from "@/lib/api";

export default async function ProjectDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const projectId = Number(id);
  const [project, datasetsPage] = await Promise.all([
    getProject(projectId),
    listDatasets(projectId, { limit: 200 }),
  ]);

  return (
    <>
      <Header title={project.name} />
      <main className="mx-auto max-w-6xl px-8 py-8">
        <ProjectSettingsCard project={project} />

        <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
          <div className="flex flex-col gap-3">
            <p className="text-sm font-medium text-content">데이터셋</p>
            {datasetsPage.items.length === 0 && (
              <p className="text-sm text-content-muted">
                아직 데이터셋이 없습니다. 업로드하면 자동으로 만들어지거나, 오른쪽에서
                직접 만들 수 있습니다.
              </p>
            )}
            {datasetsPage.items.map((d) => (
              <Link key={d.id} href={`/datasets/${d.id}`}>
                <Card className="transition-colors hover:border-accent">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-medium text-content">{d.name}</p>
                      <p className="text-sm text-content-subtle">{d.version}</p>
                    </div>
                    <Badge status={d.status} />
                  </div>
                </Card>
              </Link>
            ))}
          </div>
          <Card>
            <p className="mb-4 text-sm font-medium text-content">새 데이터셋</p>
            <DatasetCreateForm projectId={projectId} />
          </Card>
        </div>

        <div className="mt-6">
          <DangerDeleteCard
            kind="project"
            id={projectId}
            name={project.name}
            redirectTo="/projects"
          />
        </div>
      </main>
    </>
  );
}
