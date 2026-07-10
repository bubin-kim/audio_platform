"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { createDataset } from "@/lib/api";

export function DatasetCreateForm({ projectId }: { projectId: number }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [version, setVersion] = useState("v1");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const dataset = await createDataset(projectId, { name, version });
      router.push(`/datasets/${dataset.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "알 수 없는 오류");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      <div>
        <label className="text-xs text-content-subtle">이름</label>
        <input
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="v1 초기수집"
          className="mt-1 w-full rounded border border-border px-2 py-1.5 text-sm"
        />
      </div>
      <div>
        <label className="text-xs text-content-subtle">버전</label>
        <input
          value={version}
          onChange={(e) => setVersion(e.target.value)}
          className="mt-1 w-full rounded border border-border px-2 py-1.5 text-sm"
        />
      </div>
      {error && <p className="text-sm text-status-error">{error}</p>}
      <Button type="submit" disabled={submitting}>
        {submitting ? "생성 중..." : "데이터셋 생성"}
      </Button>
    </form>
  );
}
