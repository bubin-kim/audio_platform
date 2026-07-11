/**
 * 원형 게이지(도넛 미터) — 단일 비율 표시용.
 * dataviz 규칙: 트랙은 같은 램프의 옅은 단계(accent-soft), 채움은 accent,
 * 중앙 값 텍스트는 텍스트 토큰(content) — 색은 전부 tailwind 토큰(currentColor 경유).
 */
export function CircularGauge({
  ratio,
  size = 96,
  label,
}: {
  ratio: number | null;
  size?: number;
  label?: string;
}) {
  const pct = ratio === null ? 0 : Math.min(1, Math.max(0, ratio));
  const stroke = 10;
  const r = (size - stroke) / 2;
  const circumference = 2 * Math.PI * r;
  const dash = circumference * pct;

  return (
    <div className="relative inline-flex" style={{ width: size, height: size }}>
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label={label ?? `진행률 ${ratio === null ? "-" : Math.round(pct * 100) + "%"}`}
      >
        {/* 트랙: 같은 램프의 옅은 단계 */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth={stroke}
          className="stroke-accent-soft"
        />
        {/* 채움: 12시 방향 시작, 시계방향. 끝은 둥글게(rounded data end) */}
        {pct > 0 && (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            strokeWidth={stroke}
            strokeLinecap="round"
            className="stroke-accent transition-[stroke-dasharray]"
            strokeDasharray={`${dash} ${circumference - dash}`}
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
          />
        )}
      </svg>
      {/* 값 텍스트는 시리즈 색이 아닌 텍스트 토큰 */}
      <span className="absolute inset-0 flex items-center justify-center text-sm font-semibold text-content">
        {ratio === null ? "—" : `${Math.round(pct * 100)}%`}
      </span>
    </div>
  );
}
