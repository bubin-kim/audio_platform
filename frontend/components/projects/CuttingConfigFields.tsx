"use client";

/** 커팅 방식 선택 + 방식별 파라미터 입력.
 *
 * 방식별 폼 정의는 아래 CUTTING_MODES 데이터가 전부다 — 새 전략이 백엔드 registry에
 * 추가되면 여기 항목 하나만 더하면 된다(컴포넌트 코드에 방식 분기 없음, P1).
 */

type CuttingParamField = {
  key: string;
  label: string;
  required?: boolean;
  step?: number;
  placeholder?: string; // 비웠을 때 적용되는 백엔드 기본값 안내
  /** "bool"이면 체크박스로 렌더링 (기본은 숫자 입력) */
  type?: "number" | "bool";
  hint?: string; // 체크박스 아래 설명
};

export const CUTTING_MODES: {
  value: string;
  label: string;
  fields: CuttingParamField[];
}[] = [
  {
    value: "fixed_interval",
    label: "고정 간격 — 일정한 길이로 자르기",
    fields: [
      {
        key: "interval_sec",
        label: "커팅 간격(초)",
        required: true,
        step: 0.1,
        placeholder: "예: 3",
      },
      {
        key: "drop_last_shorter_than_sec",
        label: "마지막 조각 버리는 기준(초, 선택)",
        step: 0.1,
        placeholder: "비우면 유지",
      },
    ],
  },
  {
    value: "silence_based",
    label: "무음 기준 — 소리 구간 단위로 자르기",
    fields: [
      {
        key: "silence_threshold_db",
        label: "무음 판정 기준(dBFS)",
        step: 1,
        placeholder: "기본 -40",
      },
      {
        key: "min_silence_sec",
        label: "최소 무음 길이(초)",
        step: 0.05,
        placeholder: "기본 0.3",
      },
      {
        key: "min_segment_sec",
        label: "최소 조각 길이(초)",
        step: 0.05,
        placeholder: "기본 0.2",
      },
      {
        key: "max_segment_sec",
        label: "최대 조각 길이(초, 선택)",
        step: 0.5,
        placeholder: "비우면 제한 없음",
      },
      {
        key: "padding_sec",
        label: "조각 앞뒤 여유(초)",
        step: 0.05,
        placeholder: "기본 0.1",
      },
    ],
  },
  {
    value: "event_detection",
    label: "이벤트 검출 — 소리 나는 지점만 찾아 자르기",
    fields: [
      {
        key: "before_sec",
        label: "이벤트 앞 여유(초)",
        step: 0.5,
        placeholder: "기본 3",
      },
      {
        key: "after_sec",
        label: "이벤트 뒤 여유(초)",
        step: 0.5,
        placeholder: "기본 3",
      },
      {
        key: "band_low_hz",
        label: "탐지 대역 하한(Hz)",
        step: 50,
        placeholder: "기본 1900",
      },
      {
        key: "band_high_hz",
        label: "탐지 대역 상한(Hz)",
        step: 50,
        placeholder: "기본 2100",
      },
      {
        key: "height_db",
        label: "탐지 민감도(dB — 낮출수록 많이 잡음)",
        step: 0.5,
        placeholder: "기본 5 (검증값)",
      },
      {
        key: "min_gap_sec",
        label: "이벤트 최소 간격(초)",
        step: 0.5,
        placeholder: "기본 4 (검증값)",
      },
    ],
  },
];

/** Project.cutting_params(숫자) → 폼 입력값(문자열). */
export function paramsToStrings(
  params: Record<string, unknown>,
): Record<string, string> {
  return Object.fromEntries(
    Object.entries(params).map(([k, v]) => [k, v == null ? "" : String(v)]),
  );
}

/** 폼 입력값 → cutting_params. 선택한 방식의 필드만, 채워진 값만 담는다. */
export function stringsToParams(
  mode: string,
  values: Record<string, string>,
): Record<string, number | boolean> {
  const fields = CUTTING_MODES.find((m) => m.value === mode)?.fields ?? [];
  const out: Record<string, number | boolean> = {};
  for (const f of fields) {
    const raw = (values[f.key] ?? "").trim();
    if (f.type === "bool") {
      if (raw === "true") out[f.key] = true;
      continue;
    }
    if (raw !== "" && !Number.isNaN(Number(raw))) out[f.key] = Number(raw);
  }
  return out;
}

export function CuttingConfigFields({
  mode,
  values,
  onModeChange,
  onValuesChange,
}: {
  mode: string;
  values: Record<string, string>;
  onModeChange: (mode: string) => void;
  onValuesChange: (values: Record<string, string>) => void;
}) {
  const def = CUTTING_MODES.find((m) => m.value === mode) ?? CUTTING_MODES[0];
  return (
    <div className="flex flex-col gap-2">
      <select
        value={def.value}
        onChange={(e) => onModeChange(e.target.value)}
        className="w-full rounded border border-border px-2 py-1.5 text-sm"
      >
        {CUTTING_MODES.map((m) => (
          <option key={m.value} value={m.value}>
            {m.label}
          </option>
        ))}
      </select>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {def.fields.map((f) =>
          f.type === "bool" ? (
            <div key={f.key} className="sm:col-span-2">
              <label className="flex items-center gap-2 text-sm text-content">
                <input
                  type="checkbox"
                  checked={values[f.key] === "true"}
                  onChange={(e) =>
                    onValuesChange({
                      ...values,
                      [f.key]: e.target.checked ? "true" : "",
                    })
                  }
                  className="rounded border-border"
                />
                {f.label}
              </label>
              {f.hint && (
                <p className="mt-1 text-xs text-content-subtle">{f.hint}</p>
              )}
            </div>
          ) : (
            <div key={f.key}>
              <label className="text-xs text-content-subtle">{f.label}</label>
              <input
                type="number"
                required={f.required}
                step={f.step}
                placeholder={f.placeholder}
                value={values[f.key] ?? ""}
                onChange={(e) =>
                  onValuesChange({ ...values, [f.key]: e.target.value })
                }
                className="mt-1 w-full rounded border border-border px-2 py-1.5 text-sm"
              />
            </div>
          ),
        )}
      </div>
    </div>
  );
}
