import { Card } from "@/components/ui/Card";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { formatRatio } from "@/lib/format";

export function ProgressStat({
  title,
  current,
  target,
  ratio,
}: {
  title: string;
  current: string;
  target: string | null;
  ratio: number | null;
}) {
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
