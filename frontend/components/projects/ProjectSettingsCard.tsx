"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { LabelSchemaEditor } from "@/components/projects/LabelSchemaEditor";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { updateProject } from "@/lib/api";
import type { LabelFieldSchema, Project } from "@/lib/types";

/** 프로젝트 설정 표시 + 수정. 수집을 시작한 뒤에도 커팅 간격·파일명 규칙 등을
 *  바꿀 수 있다 — 변경은 이후 커팅/네이밍부터 적용되고, 기존 세그먼트는 그대로다. */
export function ProjectSettingsCard({ project }: { project: Project }) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(project.name);
  const [domain, setDomain] = useState(project.domain ?? "");
  const [namingPattern, setNamingPattern] = useState(project.naming_pattern);
  const [intervalSec, setIntervalSec] = useState(
    Number(project.cutting_params.interval_sec ?? 3),
  );
  const [targetDurationSec, setTargetDurationSec] = useState(
    project.target_duration_sec != null ? String(project.target_duration_sec) : "",
  );
  const [labelSchema, setLabelSchema] = useState<LabelFieldSchema[]>(
    project.label_schema,
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function startEditing() {
    // 서버의 현재 값으로 폼을 다시 채운다(이전 편집 취소 잔여값 제거).
    setName(project.name);
    setDomain(project.domain ?? "");
    setNamingPattern(project.naming_pattern);
    setIntervalSec(Number(project.cutting_params.interval_sec ?? 3));
    setTargetDurationSec(
      project.target_duration_sec != null ? String(project.target_duration_sec) : "",
    );
    setLabelSchema(project.label_schema);
    setError(null);
    setEditing(true);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await updateProject(project.id, {
        name,
        domain: domain || null,
        cutting_params: { ...project.cutting_params, interval_sec: intervalSec },
        naming_pattern: namingPattern,
        label_schema: labelSchema,
        target_duration_sec: targetDurationSec ? Number(targetDurationSec) : null,
      });
      setEditing(false);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "알 수 없는 오류");
    } finally {
      setSubmitting(false);
    }
  }

  if (!editing) {
    return (
      <Card>
        <div className="flex items-start justify-between gap-4">
          <div className="grid flex-1 grid-cols-2 gap-4 text-sm md:grid-cols-4">
            <div className="min-w-0">
              <p className="text-content-subtle">도메인</p>
              <p className="mt-1 break-words text-content">
                {project.domain ?? "—"}
              </p>
            </div>
            <div className="min-w-0">
              <p className="text-content-subtle">커팅 방식</p>
              <p className="mt-1 break-words text-content">
                {project.cutting_mode} (
                {Number(project.cutting_params.interval_sec ?? "—")}초)
              </p>
            </div>
            <div className="min-w-0">
              <p className="text-content-subtle">파일명 규칙</p>
              <p className="mt-1 break-words text-content">
                {project.naming_pattern}
              </p>
            </div>
            <div className="min-w-0">
              <p className="text-content-subtle">목표 녹음시간</p>
              <p className="mt-1 break-words text-content">
                {project.target_duration_sec ?? "—"}
              </p>
            </div>
          </div>
          <Button type="button" variant="secondary" onClick={startEditing}>
            설정 수정
          </Button>
        </div>
        {project.label_schema.length > 0 && (
          <div className="mt-4">
            <p className="text-sm text-content-subtle">라벨 스키마</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {project.label_schema.map((f) => (
                <span
                  key={f.key}
                  className="rounded-full bg-surface-muted px-3 py-1 text-xs text-content-muted"
                >
                  {f.key} ({f.type}
                  {f.required ? ", 필수" : ""})
                </span>
              ))}
            </div>
          </div>
        )}
      </Card>
    );
  }

  return (
    <Card>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <p className="text-sm font-medium text-content">프로젝트 설정 수정</p>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div>
            <label className="text-xs text-content-subtle">이름</label>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 w-full rounded border border-border px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-content-subtle">도메인 태그</label>
            <input
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              placeholder="예: heart, vehicle"
              className="mt-1 w-full rounded border border-border px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-content-subtle">파일명 규칙</label>
            <input
              required
              value={namingPattern}
              onChange={(e) => setNamingPattern(e.target.value)}
              className="mt-1 w-full rounded border border-border px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-content-subtle">
              커팅 간격(초) — {project.cutting_mode}
            </label>
            <input
              required
              type="number"
              min={0.1}
              step={0.1}
              value={intervalSec}
              onChange={(e) => setIntervalSec(Number(e.target.value))}
              className="mt-1 w-full rounded border border-border px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-content-subtle">
              목표 총 녹음시간(초, 선택)
            </label>
            <input
              type="number"
              min={1}
              value={targetDurationSec}
              onChange={(e) => setTargetDurationSec(e.target.value)}
              className="mt-1 w-full rounded border border-border px-2 py-1.5 text-sm"
            />
          </div>
        </div>
        <div>
          <label className="text-xs text-content-subtle">라벨 스키마</label>
          <p className="mt-0.5 text-xs text-content-subtle">
            변경은 이후 커팅부터 적용됩니다. 이미 만들어진 세그먼트의 라벨은 바뀌지
            않습니다.
          </p>
          <div className="mt-1">
            <LabelSchemaEditor value={labelSchema} onChange={setLabelSchema} />
          </div>
        </div>
        {error && <p className="text-sm text-status-error">{error}</p>}
        <div className="flex gap-2">
          <Button type="submit" disabled={submitting}>
            {submitting ? "저장 중..." : "저장"}
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => setEditing(false)}
          >
            취소
          </Button>
        </div>
      </form>
    </Card>
  );
}
