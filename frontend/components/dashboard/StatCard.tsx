import { Card } from "@/components/ui/Card";

export function StatCard({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  /** tailwind.config.ts의 chip 팔레트 클래스(예: "bg-chip-1"). 생략하면 기본 카드색. */
  tone?: string;
}) {
  // 톤 배경(특히 chip-3처럼 어두운 파스텔)에서는 text-content-subtle이 배경과
  // 거의 같은 밝기라 안 보인다 — 톤이 있으면 라벨도 진한 톤(text-content)으로.
  return (
    <Card className={tone}>
      <p className={`text-sm ${tone ? "text-content" : "text-content-subtle"}`}>
        {label}
      </p>
      <p className="mt-2 text-2xl font-semibold text-content">{value}</p>
      {sub && <p className="mt-1 text-xs text-content-muted">{sub}</p>}
    </Card>
  );
}
