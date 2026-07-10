type Tone = "ok" | "warn" | "error" | "neutral";

const TONE_CLASS: Record<Tone, string> = {
  ok: "bg-status-ok/10 text-status-ok",
  warn: "bg-status-warn/10 text-status-warn",
  error: "bg-status-error/10 text-status-error",
  neutral: "bg-surface-muted text-content-muted",
};

// Dataset.status / Job.status 문자열 → 뱃지 톤. 도메인이 아니라 상태값 기준(P1과 무관).
const STATUS_TONE: Record<string, Tone> = {
  collecting: "neutral",
  processing: "warn",
  ready: "ok",
  queued: "neutral",
  running: "warn",
  done: "ok",
  failed: "error",
};

export function Badge({ status }: { status: string }) {
  const tone = STATUS_TONE[status] ?? "neutral";
  return (
    <span
      className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${TONE_CLASS[tone]}`}
    >
      {status}
    </span>
  );
}
