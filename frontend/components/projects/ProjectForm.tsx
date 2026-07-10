"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

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
  const [intervalSec, setIntervalSec] = useState(3);
  const [targetDurationSec, setTargetDurationSec] = useState("");
  const [labelSchema, setLabelSchema] = useState<LabelFieldSchema[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const project = await createProject({
        name,
        domain: domain || null,
        cutting_mode: "fixed_interval",
        cutting_params: { interval_sec: intervalSec },
        naming_pattern: namingPattern,
        label_schema: labelSchema,
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
        <label className="text-xs text-content-subtle">
          커팅 간격(초) — fixed_interval
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
      {error && <p className="text-sm text-status-error">{error}</p>}
      <Button type="submit" disabled={submitting}>
        {submitting ? "생성 중..." : "프로젝트 생성"}
      </Button>
    </form>
  );
}
