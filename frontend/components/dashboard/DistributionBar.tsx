import { Card } from "@/components/ui/Card";

/** sample_rate/format 분포처럼 { 라벨: 개수 } 형태를 가로 막대로 보여준다. */
export function DistributionBar({
  title,
  distribution,
}: {
  title: string;
  distribution: Record<string, number>;
}) {
  const entries = Object.entries(distribution).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, count]) => count));

  return (
    <Card>
      <p className="text-sm text-content-subtle">{title}</p>
      {entries.length === 0 ? (
        <p className="mt-3 text-sm text-content-muted">데이터 없음</p>
      ) : (
        <div className="mt-4 flex flex-col gap-3">
          {entries.map(([key, count]) => (
            <div key={key}>
              <div className="flex justify-between text-xs text-content-muted">
                <span>{key}</span>
                <span>{count}</span>
              </div>
              <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-surface-muted">
                <div
                  className="h-full rounded-full bg-accent"
                  style={{ width: `${(count / max) * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
