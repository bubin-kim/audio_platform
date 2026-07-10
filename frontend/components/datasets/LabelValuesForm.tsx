"use client";

import type { LabelFieldSchema } from "@/lib/types";

/** 이미 정의된 label_schema에 값을 채우는 폼(커팅 시 common_labels 입력용). */
export function LabelValuesForm({
  schema,
  values,
  onChange,
}: {
  schema: LabelFieldSchema[];
  values: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}) {
  if (schema.length === 0) {
    return (
      <p className="text-sm text-content-muted">
        이 프로젝트는 공통 라벨(label_schema)이 없습니다.
      </p>
    );
  }

  const set = (key: string, value: unknown) => onChange({ ...values, [key]: value });

  return (
    <div className="flex flex-col gap-2">
      {schema.map((field) => (
        <div key={field.key}>
          <label className="text-xs text-content-subtle">
            {field.key}
            {field.required && " *"}
          </label>
          {field.type === "enum" ? (
            <select
              className="mt-1 w-full rounded border border-border px-2 py-1.5 text-sm"
              value={(values[field.key] as string) ?? ""}
              onChange={(e) => set(field.key, e.target.value)}
            >
              <option value="">선택 안 함</option>
              {(field.options ?? []).map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          ) : field.type === "bool" ? (
            <input
              type="checkbox"
              checked={Boolean(values[field.key])}
              onChange={(e) => set(field.key, e.target.checked)}
              className="mt-1 block"
            />
          ) : (
            <input
              type={field.type === "number" ? "number" : "text"}
              value={(values[field.key] as string | number | undefined) ?? ""}
              onChange={(e) =>
                set(
                  field.key,
                  field.type === "number" ? Number(e.target.value) : e.target.value,
                )
              }
              className="mt-1 w-full rounded border border-border px-2 py-1.5 text-sm"
            />
          )}
        </div>
      ))}
    </div>
  );
}
