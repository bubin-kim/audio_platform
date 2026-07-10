import { Header } from "@/components/layout/Header";
import { Card } from "@/components/ui/Card";
import { UploadForm } from "@/components/upload/UploadForm";
import { listProjects } from "@/lib/api";

export default async function UploadPage() {
  const { items: projects } = await listProjects({ limit: 200 });

  return (
    <>
      <Header title="업로드" />
      <main className="mx-auto max-w-2xl px-8 py-8">
        <Card>
          <UploadForm projects={projects} />
        </Card>
      </main>
    </>
  );
}
