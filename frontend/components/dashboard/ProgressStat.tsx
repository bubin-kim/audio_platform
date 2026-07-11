import { Card } from "@/components/ui/Card";
import { CircularGauge } from "@/components/ui/CircularGauge";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { formatRatio } from "@/lib/format";

export function ProgressStat({
  title,
  current,
  target,
  ratio,
  variant = "bar",
}: {
  title: string;
  current: string;
  target: string | null;
  ratio: number | null;
  /** bar: 가로 막대(기본) / gauge: 원형 게이지 */
  variant?: "bar" | "gauge";
}) {
  if (variant === "gauge") {
    return (
      <Card>
        <div className="flex items-center gap-5">
          <CircularGauge ratio={ratio} label={`${title} ${formatRatio(ratio)}`} />
          <div>
            <p className="text-sm text-content-subtle">{title}</p>
            <p className="mt-1 text-sm text-content-muted">
              {current}
              {target && ` / 목표 ${target}`}
            </p>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <div className="flex items-baseline justify-between">
        <p className="text-sm text-content-subtle">{title}</p>
        <p className="text-sm font-medium text-content">{formatRatio(ratio)}</p>
      </div>
      <p className="mt-2 text-sm text-content-muted">
        {current}
        {target && ` / 목표 ${target}`}
      </p>
      <div className="mt-3">
        <ProgressBar ratio={ratio} />
      </div>
    </Card>
  );
}
