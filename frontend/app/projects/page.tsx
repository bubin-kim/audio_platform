import Link from "next/link";

import { Header } from "@/components/layout/Header";
import { ProjectForm } from "@/components/projects/ProjectForm";
import { Card } from "@/components/ui/Card";
import { listProjects } from "@/lib/api";

export default async function ProjectsPage() {
  const { items: projects } = await listProjects({ limit: 200 });

  return (
    <>
      <Header title="프로젝트" />
      <main className="mx-auto max-w-6xl px-8 py-8">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_360px]">
          <div className="flex flex-col gap-3">
            {projects.length === 0 && (
              <p className="text-sm text-content-muted">
                아직 프로젝트가 없습니다. 오른쪽에서 새로 만들어 보세요.
              </p>
            )}
            {projects.map((p) => (
              <Link key={p.id} href={`/projects/${p.id}`}>
                <Card className="transition-colors hover:border-accent">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-medium text-content">{p.name}</p>
                      <p className="text-sm text-content-subtle">
                        {p.domain ?? "도메인 미지정"} · {p.cutting_mode}
                      </p>
                    </div>
                    <p className="text-xs text-content-subtle">
                      {new Date(p.created_at).toLocaleDateString("ko-KR")}
                    </p>
                  </div>
                </Card>
              </Link>
            ))}
          </div>
          <Card>
            <p className="mb-4 text-sm font-medium text-content">새 프로젝트</p>
            <ProjectForm />
          </Card>
        </div>
      </main>
    </>
  );
}
