/**
 * 백엔드 REST 호출 모음 — 모든 fetch는 여기 한 곳에 집중한다(03 §2).
 * 컴포넌트는 이 모듈의 함수만 부르고, 직접 fetch 하지 않는다.
 * 주소가 바뀌어도 이 파일만 고치면 된다.
 */

import { getClientToken } from "@/lib/auth";
import type {
  Dataset,
  DatasetCreate,
  Job,
  Page,
  ProcessRequest,
  Project,
  ProjectCreate,
  Segment,
  StatsResponse,
  UploadResult,
  Waveform,
} from "@/lib/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8100/api";

/** API 에러 — HTTP status를 함께 던져 호출자가 409(충돌) 등을 분기할 수 있게 한다. */
export class ApiRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

/** 액세스 토큰 헤더 (docs/13 §6). 브라우저는 쿠키에서, SSR은 next/headers에서 읽는다. */
async function authHeaders(): Promise<Record<string, string>> {
  let token: string | undefined;
  if (typeof window === "undefined") {
    try {
      // 서버 컴포넌트 전용 모듈이라 동적 import (클라이언트 번들에서 실행되지 않음)
      const { cookies } = await import("next/headers");
      token = (await cookies()).get("access_token")?.value;
    } catch {
      token = undefined; // 요청 컨텍스트 밖(빌드 등)에서는 토큰 없음
    }
  } else {
    token = getClientToken();
  }
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** 미디어 URL(<audio src>·<a href>)은 헤더를 못 붙이므로 쿼리 토큰을 부착한다. */
function withToken(url: string): string {
  if (typeof window === "undefined") return url;
  const token = getClientToken();
  if (!token) return url;
  return `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(token)}`;
}

/** 공통 요청 헬퍼. 에러 응답(ErrorResponse)을 표준화해 던진다.
 *
 * 대시보드류 데이터는 자주 바뀌므로 기본은 캐시하지 않는다(no-store).
 * FormData 바디는 브라우저가 boundary를 채운 Content-Type을 스스로 붙이도록
 * 기본 JSON 헤더를 건너뛴다. 204(No Content)는 본문 파싱 없이 undefined를 돌려준다.
 * 401 수신 시(브라우저) 토큰 입력 화면으로 보낸다.
 */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isFormData = init?.body instanceof FormData;
  const auth = await authHeaders();
  const res = await fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    ...init,
    headers: isFormData
      ? { ...auth, ...(init?.headers ?? {}) }
      : { "Content-Type": "application/json", ...auth, ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    if (res.status === 401 && typeof window !== "undefined") {
      window.location.href = "/login";
    }
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiRequestError(
      detail.detail ?? `Request failed: ${res.status}`,
      res.status,
    );
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

/** 로그인 화면에서 토큰 유효성 확인 — 401 리다이렉트 없이 직접 검사한다. */
export async function verifyToken(token: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/projects?limit=1`, {
      cache: "no-store",
      headers: { Authorization: `Bearer ${token}` },
    });
    return res.ok;
  } catch {
    return false;
  }
}

function qs(params: Record<string, string | number | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined);
  if (entries.length === 0) return "";
  return `?${new URLSearchParams(entries as [string, string][]).toString()}`;
}

// --- 헬스체크 ---
export function getHealth(): Promise<{ status: string }> {
  const base = API_BASE.replace(/\/api$/, "");
  return fetch(`${base}/health`, { cache: "no-store" }).then((r) => r.json());
}

// --- Project ---
export const listProjects = (params?: { limit?: number; offset?: number }) =>
  request<Page<Project>>(`/projects${qs(params ?? {})}`);

export const getProject = (id: number) => request<Project>(`/projects/${id}`);

export const createProject = (body: ProjectCreate) =>
  request<Project>("/projects", {
    method: "POST",
    body: JSON.stringify(body),
  });

export const updateProject = (id: number, body: Partial<ProjectCreate>) =>
  request<Project>(`/projects/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });

// --- Dataset ---
export const listDatasets = (
  projectId: number,
  params?: { limit?: number; offset?: number },
) => request<Page<Dataset>>(`/projects/${projectId}/datasets${qs(params ?? {})}`);

export const createDataset = (projectId: number, body: DatasetCreate) =>
  request<Dataset>(`/projects/${projectId}/datasets`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const getDataset = (id: number) => request<Dataset>(`/datasets/${id}`);

export const listSegments = (
  datasetId: number,
  params?: { limit?: number; offset?: number },
) => request<Page<Segment>>(`/datasets/${datasetId}/segments${qs(params ?? {})}`);

// --- 삭제 (docs/06 §5.2 — 데이터셋·프로젝트는 이름 재입력 확인이 필수) ---
export const deleteSegment = (id: number) =>
  request<void>(`/segments/${id}`, { method: "DELETE" });

export const deleteDataset = (id: number, confirmName: string) =>
  request<void>(`/datasets/${id}${qs({ confirm: confirmName })}`, {
    method: "DELETE",
  });

export const deleteProject = (id: number, confirmName: string) =>
  request<void>(`/projects/${id}${qs({ confirm: confirmName })}`, {
    method: "DELETE",
  });

/** 개별 세그먼트 라벨 예외 보정 (06_API.md §8) — 기존 라벨 위에 부분 덮어쓰기. */
export const updateSegmentLabels = (
  segmentId: number,
  labels: Record<string, unknown>,
) =>
  request<Segment>(`/segments/${segmentId}/labels`, {
    method: "PATCH",
    body: JSON.stringify({ labels }),
  });

/** 세그먼트 오디오는 브라우저 <audio>가 직접 스트리밍하는 URL이다. */
export const segmentAudioUrl = (segmentId: number) =>
  withToken(`${API_BASE}/segments/${segmentId}/audio`);

/** 미니 파형 피크 (06_API.md §4.5). 불변 데이터라 브라우저 캐시 허용. */
export const getSegmentWaveform = (segmentId: number) =>
  request<Waveform>(`/segments/${segmentId}/waveform`, { cache: "force-cache" });

// --- Upload ---
export const uploadFiles = (
  projectId: number,
  files: File[],
  datasetId?: number,
  uploadedBy?: string,
): Promise<UploadResult> => {
  const form = new FormData();
  form.set("project_id", String(projectId));
  if (datasetId !== undefined) form.set("dataset_id", String(datasetId));
  if (uploadedBy) form.set("uploaded_by", uploadedBy);
  for (const f of files) form.append("files", f);
  return request<UploadResult>("/uploads", { method: "POST", body: form });
};

// --- Processing / Job ---
export const startProcessing = (datasetId: number, body?: ProcessRequest) =>
  request<Job>(`/datasets/${datasetId}/process`, {
    method: "POST",
    body: JSON.stringify(body ?? {}),
  });

export const getJob = (id: number) => request<Job>(`/jobs/${id}`);

export const listJobs = (
  datasetId: number,
  params?: { limit?: number; offset?: number },
) => request<Page<Job>>(`/datasets/${datasetId}/jobs${qs(params ?? {})}`);

// --- Export ---
export const startExport = (datasetId: number) =>
  request<Job>(`/datasets/${datasetId}/export`);

/** 다운로드는 JSON 왕복이 아니라 브라우저가 직접 여는 URL이다(<a href>). */
export const downloadExportUrl = (datasetId: number) =>
  withToken(`${API_BASE}/datasets/${datasetId}/export/download`);

// --- Stats ---
export const getStats = (projectId?: number) =>
  request<StatsResponse>(`/stats${qs({ project_id: projectId })}`);

export { request };
