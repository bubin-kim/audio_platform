"use client";

import type { LabelFieldSchema, LabelType } from "@/lib/types";

const TYPES: LabelType[] = ["string", "number", "bool", "enum"];

/** Project.label_schema를 정의하는 폼(도메인 무관 — 필드 이름/타입은 사용자가 정한다, P1). */
export function LabelSchemaEditor({
  value,
  onChange,
}: {
  value: LabelFieldSchema[];
  onChange: (next: LabelFieldSchema[]) => void;
}) {
  const update = (i: number, patch: Partial<LabelFieldSchema>) =>
    onChange(value.map((f, idx) => (idx === i ? { ...f, ...patch } : f)));
  const remove = (i: number) => onChange(value.filter((_, idx) => idx !== i));
  const add = () =>
    onChange([
      ...value,
      { key: "", type: "string", required: false, options: null },
    ]);

  return (
    <div className="flex flex-col gap-2">
      {value.map((field, i) => (
        <div
          key={i}
          className="flex flex-wrap items-center gap-2 rounded-md border border-border p-2"
        >
          <input
            className="w-28 rounded border border-border px-2 py-1 text-sm"
            placeholder="key"
            value={field.key}
            onChange={(e) => update(i, { key: e.target.value })}
          />
          <select
            className="rounded border border-border px-2 py-1 text-sm"
            value={field.type}
            onChange={(e) =>
              update(i, {
                type: e.target.value as LabelType,
                options: e.target.value === "enum" ? (field.options ?? [""]) : null,
              })
            }
          >
            {TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-1 text-xs text-content-muted">
            <input
              type="checkbox"
              checked={field.required}
              onChange={(e) => update(i, { required: e.target.checked })}
            />
            필수
          </label>
          {field.type === "enum" && (
            <input
              className="min-w-40 flex-1 rounded border border-border px-2 py-1 text-sm"
              placeholder="옵션(쉼표로 구분): N,S,E,W"
              value={(field.options ?? []).join(",")}
              onChange={(e) =>
                update(i, {
                  options: e.target.value
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean),
                })
              }
            />
          )}
          <button
            type="button"
            onClick={() => remove(i)}
            className="ml-auto text-xs text-status-error hover:underline"
          >
            삭제
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={add}
        className="self-start text-sm text-accent hover:underline"
      >
        + 라벨 필드 추가
      </button>
    </div>
  );
}
