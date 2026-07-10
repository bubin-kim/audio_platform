"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { listDatasets, uploadFiles } from "@/lib/api";
import type { Dataset, Project, UploadResult } from "@/lib/types";

export function UploadForm({ projects }: { projects: Project[] }) {
  const router = useRouter();
  const [projectId, setProjectId] = useState<number | "">(projects[0]?.id ?? "");
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [datasetId, setDatasetId] = useState<number | "">("");
  const [files, setFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (projectId === "") {
      setDatasets([]);
      return;
    }
    listDatasets(projectId, { limit: 200 })
      .then((page) => setDatasets(page.items))
      .catch(() => setDatasets([]));
    setDatasetId("");
  }, [projectId]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (projectId === "" || files.length === 0) return;
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const res = await uploadFiles(
        projectId,
        files,
        datasetId === "" ? undefined : datasetId,
      );
      setResult(res);
      setFiles([]);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "알 수 없는 오류");
    } finally {
      setSubmitting(false);
    }
  }

  /** 드롭·Browse 어느 쪽으로 담아도 이름 기준으로 합친다(중복 담기 방지). */
  function addFiles(incoming: FileList | File[]) {
    // input.files의 FileList는 live라서 input.value = ""로 비우면 함께 비워진다.
    // setFiles 콜백(비동기) 안에서 읽기 전에 여기서 즉시 배열로 스냅샷을 뜬다.
    const snapshot = Array.from(incoming);
    setFiles((prev) => {
      const byName = new Map(prev.map((f) => [f.name, f]));
      for (const f of snapshot) byName.set(f.name, f);
      return Array.from(byName.values());
    });
  }

  function removeFile(name: string) {
    setFiles((prev) => prev.filter((f) => f.name !== name));
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files.length > 0) addFiles(e.dataTransfer.files);
  }

  if (projects.length === 0) {
    return (
      <p className="text-sm text-content-muted">
        먼저{" "}
        <Link href="/projects" className="text-accent hover:underline">
          프로젝트
        </Link>
        를 만들어야 업로드할 수 있습니다.
      </p>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div>
        <label className="text-xs text-content-subtle">프로젝트</label>
        <select
          value={projectId}
          onChange={(e) => setProjectId(Number(e.target.value))}
          className="mt-1 w-full rounded border border-border px-2 py-1.5 text-sm"
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="text-xs text-content-subtle">
          데이터셋 (선택 — 비우면 기본 데이터셋 자동 생성/재사용)
        </label>
        <select
          value={datasetId}
          onChange={(e) =>
            setDatasetId(e.target.value ? Number(e.target.value) : "")
          }
          className="mt-1 w-full rounded border border-border px-2 py-1.5 text-sm"
        >
          <option value="">자동 (기본 데이터셋)</option>
          {datasets.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name} ({d.version})
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="text-xs text-content-subtle">
          오디오 파일 (wav/mp3/flac/m4a, 다중 선택 가능)
        </label>
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          className={`mt-1 flex flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed px-4 py-8 text-center transition-colors ${
            isDragging
              ? "border-accent bg-accent-soft"
              : "border-border bg-surface-muted"
          }`}
        >
          <p className="text-sm text-content-muted">Drop files here</p>
          <p className="text-xs text-content-subtle">or</p>
          <Button
            type="button"
            variant="secondary"
            onClick={() => fileInputRef.current?.click()}
          >
            Browse Files
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".wav,.mp3,.flac,.m4a,audio/*"
            onChange={(e) => {
              if (e.target.files) addFiles(e.target.files);
              e.target.value = "";
            }}
            className="hidden"
          />
        </div>
        {files.length > 0 && (
          <ul className="mt-2 flex flex-col gap-1">
            {files.map((f) => (
              <li
                key={f.name}
                className="flex items-center justify-between rounded border border-border px-2 py-1 text-xs text-content-muted"
              >
                <span>{f.name}</span>
                <button
                  type="button"
                  onClick={() => removeFile(f.name)}
                  className="text-status-error hover:underline"
                >
                  삭제
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {error && <p className="text-sm text-status-error">{error}</p>}
      <Button type="submit" disabled={submitting}>
        {submitting ? "업로드 중..." : "업로드"}
      </Button>

      {result && (
        <div className="mt-2 rounded-md border border-border p-3">
          <p className="text-sm text-content">
            데이터셋 #{result.dataset_id}
            {result.created_dataset && " (새로 생성됨)"}에 {result.sources.length}
            개 파일 등록됨
          </p>
          <ul className="mt-2 flex flex-col gap-1 text-xs text-content-muted">
            {result.sources.map((s) => (
              <li key={s.id}>
                {s.filename} — {s.format}, {s.sample_rate}Hz,{" "}
                {s.duration_sec?.toFixed(1)}초
              </li>
            ))}
          </ul>
          <Link
            href={`/datasets/${result.dataset_id}`}
            className="mt-2 inline-block text-sm text-accent hover:underline"
          >
            데이터셋으로 이동 →
          </Link>
        </div>
      )}
    </form>
  );
}
