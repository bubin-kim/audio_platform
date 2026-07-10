export function ProgressBar({ ratio }: { ratio: number | null }) {
  const pct = ratio === null ? 0 : Math.min(100, Math.max(0, ratio * 100));
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-surface-muted">
      <div
        className="h-full rounded-full bg-accent transition-[width]"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
