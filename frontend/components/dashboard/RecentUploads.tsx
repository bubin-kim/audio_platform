import { Card } from "@/components/ui/Card";
import { formatBytes, formatDateTime } from "@/lib/format";
import type { RecentUpload } from "@/lib/types";

export function RecentUploads({ uploads }: { uploads: RecentUpload[] }) {
  return (
    <Card>
      <p className="text-sm text-content-subtle">최근 업로드</p>
      {uploads.length === 0 ? (
        <p className="mt-3 text-sm text-content-muted">아직 업로드가 없습니다.</p>
      ) : (
        <ul className="mt-3 flex flex-col divide-y divide-border">
          {uploads.map((u, i) => (
            <li
              key={`${u.filename}-${i}`}
              className="flex items-center justify-between py-2 text-sm"
            >
              <span className="text-content">
                {u.filename}
                {u.uploaded_by && (
                  <span className="ml-2 text-xs text-content-subtle">
                    {u.uploaded_by}
                  </span>
                )}
              </span>
              <span className="text-content-subtle">
                {formatDateTime(u.uploaded_at)}
                {u.file_size !== null && ` · ${formatBytes(u.file_size)}`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
