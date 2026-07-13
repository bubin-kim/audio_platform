"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import {
  CuttingConfigFields,
  stringsToParams,
} from "@/components/projects/CuttingConfigFields";
import { LabelSchemaEditor } from "@/components/projects/LabelSchemaEditor";
import { Button } from "@/components/ui/Button";
import { createProject } from "@/lib/api";
import type { LabelFieldSchema } from "@/lib/types";

// 자주 쓰는 도메인 태그를 버튼으로 빠르게 채워 넣는 프리셋. 태그일 뿐이라 목록에
// 없는 값도 "Custom"으로 자유 입력할 수 있다 — 코드가 이 값으로 분기하지 않는다(P1).
const DOMAIN_PRESETS = [
  { key: "heart", label: "Heart", emoji: "❤️" },
  { key: "vehicle", label: "Vehicle", emoji: "🚗" },
  { key: "wildlife", label: "Wildlife", emoji: "🦉" },
  { key: "industrial", label: "Industrial", emoji: "🏭" },
] as const;

/** 새 Project 생성 폼. 도메인은 태그일 뿐이고, cutting_mode/label_schema가 실제 동작을 정한다(P1). */
export function ProjectForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [isCustomDomain, setIsCustomDomain] = useState(false);
  const [namingPattern, setNamingPattern] = useState("{date}_{seq:03d}");
  const [cuttingMode, setCuttingMode] = useState("fixed_interval");
  const [cuttingValues, setCuttingValues] = useState<Record<string, string>>({
    interval_sec: "3",
  });
  const [targetDurationSec, setTargetDurationSec] = useState("");
  const [labelSchema, setLabelSchema] = useState<LabelFieldSchema[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // enum인데 유효 옵션이 없는 필드가 있으면 제출 차단 (docs/12 C1 — options:[''] 사고 방어)
  const invalidEnumKeys = labelSchema
    .filter(
      (f) =>
        f.type === "enum" &&
        (f.options ?? []).filter((o) => o.trim() !== "").length === 0,
    )
    .map((f) => f.key || "(이름 없음)");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const project = await createProject({
        name,
        domain: domain || null,
        cutting_mode: cuttingMode,
        cutting_params: stringsToParams(cuttingMode, cuttingValues),
        naming_pattern: namingPattern,
        // 빈/공백 옵션은 제출 전에 걸러낸다 (백엔드 validator와 이중 방어)
        label_schema: labelSchema.map((f) =>
          f.type === "enum"
            ? {
                ...f,
                options: (f.options ?? [])
                  .map((o) => o.trim())
                  .filter((o) => o !== ""),
              }
            : f,
        ),
        target_duration_sec: targetDurationSec ? Number(targetDurationSec) : null,
      });
      router.push(`/projects/${project.id}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "알 수 없는 오류");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div>
        <label className="text-xs text-content-subtle">이름</label>
        <input
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="예: 심음 데이터 수집"
          className="mt-1 w-full rounded border border-border px-2 py-1.5 text-sm"
        />
      </div>
      <div>
        <label className="text-xs text-content-subtle">도메인 태그 (선택)</label>
        <div className="mt-1 flex flex-wrap gap-2">
          {DOMAIN_PRESETS.map((preset) => {
            const selected = !isCustomDomain && domain === preset.key;
            return (
              <button
                key={preset.key}
                type="button"
                onClick={() => {
                  setIsCustomDomain(false);
                  setDomain(preset.key);
                }}
                className={`rounded-full border px-3 py-1.5 text-sm transition-colors ${
                  selected
                    ? "border-accent bg-accent-soft text-accent"
                    : "border-border bg-surface-card text-content-muted hover:bg-surface-muted"
                }`}
              >
                {preset.emoji} {preset.label}
              </button>
            );
          })}
          <button
            type="button"
            onClick={() => {
              setIsCustomDomain(true);
              setDomain("");
            }}
            className={`rounded-full border px-3 py-1.5 text-sm transition-colors ${
              isCustomDomain
                ? "border-accent bg-accent-soft text-accent"
                : "border-border bg-surface-card text-content-muted hover:bg-surface-muted"
            }`}
          >
            ✨ Custom
          </button>
        </div>
        {isCustomDomain && (
          <input
            autoFocus
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            placeholder="직접 입력 (예: marine, speech)"
            className="mt-2 w-full rounded border border-border px-2 py-1.5 text-sm"
          />
        )}
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
        <label className="text-xs text-content-subtle">커팅 방식</label>
        <div className="mt-1">
          <CuttingConfigFields
            mode={cuttingMode}
            values={cuttingValues}
            onModeChange={setCuttingMode}
            onValuesChange={setCuttingValues}
          />
        </div>
      </div>
      <div>
        <label className="text-xs text-content-subtle">
          목표 총 녹음시간(초, 선택 — 대시보드 진행률 분모)
        </label>
        <input
          type="number"
          min={1}
          value={targetDurationSec}
          onChange={(e) => setTargetDurationSec(e.target.value)}
          className="mt-1 w-full rounded border border-border px-2 py-1.5 text-sm"
        />
      </div>
      <div>
        <label className="text-xs text-content-subtle">라벨 스키마</label>
        <div className="mt-1">
          <LabelSchemaEditor value={labelSchema} onChange={setLabelSchema} />
        </div>
      </div>
      {invalidEnumKeys.length > 0 && (
        <p className="text-sm text-status-warn">
          enum 필드에 옵션이 필요합니다: {invalidEnumKeys.join(", ")}
        </p>
      )}
      {error && <p className="text-sm text-status-error">{error}</p>}
      <Button type="submit" disabled={submitting || invalidEnumKeys.length > 0}>
        {submitting ? "생성 중..." : "프로젝트 생성"}
      </Button>
    </form>
  );
}
