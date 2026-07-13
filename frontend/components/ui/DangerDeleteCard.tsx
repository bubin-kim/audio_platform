"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { deleteDataset, deleteProject } from "@/lib/api";

/** 이름 재입력 확인이 필요한 파괴적 삭제 (docs/06 §5.2 — confirm=이름 계약).
 *  하위 데이터·파일까지 지워지므로 대상 이름을 정확히 입력해야 버튼이 활성화된다. */
export function DangerDeleteCard({
  kind,
  id,
  name,
  redirectTo,
}: {
  kind: "dataset" | "project";
  id: number;
  name: string;
  redirectTo: string;
}) {
  const router = useRouter();
  const [typed, setTyped] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const label = kind === "dataset" ? "데이터셋" : "프로젝트";
  const scope =
    kind === "dataset"
      ? "세그먼트·원본·export CSV 파일까지"
      : "하위 데이터셋·세그먼트·원본 파일까지";

  async function handleDelete(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (kind === "dataset") await deleteDataset(id, typed);
      else await deleteProject(id, typed);
      router.push(redirectTo);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "삭제 실패");
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={handleDelete}
      className="rounded-md border border-status-error/30 p-3"
    >
      <p className="text-sm font-medium text-status-error">{label} 삭제</p>
      <p className="mt-1 text-xs text-content-muted">
        {scope} 전부 삭제되며 되돌릴 수 없습니다. 확인을 위해 {label} 이름(
        <span className="font-medium text-content">{name}</span>)을 입력하세요.
      </p>
      <div className="mt-2 flex gap-2">
        <input
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          placeholder={name}
          className="w-full rounded border border-border px-2 py-1.5 text-sm"
        />
        <Button type="submit" disabled={busy || typed !== name}>
          {busy ? "삭제 중..." : "삭제"}
        </Button>
      </div>
      {error && <p className="mt-2 text-xs text-status-error">{error}</p>}
    </form>
  );
}
