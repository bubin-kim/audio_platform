/**
 * 백엔드 Pydantic schema(docs/06_API.md)와 맞춘 타입.
 * 필드가 바뀌면 이 파일과 backend/app/schemas/*.py를 함께 맞춘다.
 */

/** 목록 응답 공통 형태 (Page[T]). */
export interface Page<T> {
  items: T[];
  total: number;
}

/** 공통 에러 응답 (ErrorResponse). */
export interface ApiError {
  detail: string;
  code?: string;
}

// --- Project ---

export type LabelType = "string" | "number" | "enum" | "bool";

export interface LabelFieldSchema {
  key: string;
  type: LabelType;
  required: boolean;
  options?: string[] | null;
}

export interface Project {
  id: number;
  name: string;
  domain: string | null;
  cutting_mode: string;
  cutting_params: Record<string, unknown>;
  naming_pattern: string;
  label_schema: LabelFieldSchema[];
  target_duration_sec: number | null;
  created_at: string;
}

export interface ProjectCreate {
  name: string;
  domain?: string | null;
  cutting_mode: string;
  cutting_params: Record<string, unknown>;
  naming_pattern: string;
  label_schema: LabelFieldSchema[];
  target_duration_sec?: number | null;
}

// --- Dataset ---

export type DatasetStatus = "collecting" | "processing" | "ready";

export interface Dataset {
  id: number;
  project_id: number;
  name: string;
  version: string;
  status: DatasetStatus;
  created_at: string;
}

export interface DatasetCreate {
  name: string;
  version?: string;
}

// --- Segment ---

export interface Segment {
  id: number;
  dataset_id: number;
  filename: string;
  storage_path: string;
  duration_sec: number;
  sample_rate: number;
  channels: number;
  bit_depth: number | null;
  file_size: number;
  format: string;
  source_start_sec: number;
  labels: Record<string, unknown>;
  is_labeled: boolean;
  created_at: string;
}

/** 미니 파형 (06_API.md §4.5). peaks는 풀스케일 기준 절대 피크 0..1. */
export interface Waveform {
  segment_id: number;
  duration_sec: number;
  peaks: number[];
}

// --- Upload ---

export interface SourceRead {
  id: number;
  filename: string;
  storage_path: string;
  duration_sec: number | null;
  sample_rate: number | null;
  channels: number | null;
  bit_depth: number | null;
  file_size: number | null;
  format: string | null;
}

export interface UploadResult {
  dataset_id: number;
  created_dataset: boolean;
  sources: SourceRead[];
}

// --- Job / Processing ---

export type JobType = "cutting" | "export";
export type JobStatus = "queued" | "running" | "done" | "failed";

export interface Job {
  id: number;
  dataset_id: number;
  type: JobType;
  status: JobStatus;
  progress: number;
  total_items: number | null;
  params: Record<string, unknown>;
  error_msg: string | null;
  result_path: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface ProcessRequest {
  source_file_ids?: number[] | null;
  params_override?: Record<string, unknown> | null;
  common_labels?: Record<string, unknown>;
  /** 기존 세그먼트가 있는 원본을 대체 재커팅 (docs/10). 기본 false → 409. */
  replace_existing?: boolean;
  /** 대체 시 겹침 매칭으로 라벨 승계 (docs/10). 기본 true. */
  inherit_labels?: boolean;
}

// --- Stats ---

export interface UploadProgress {
  current_sec: number;
  target_sec: number | null;
  ratio: number | null;
}

export interface LabelingProgress {
  labeled: number;
  total: number;
  ratio: number | null;
}

export interface RecentUpload {
  filename: string;
  uploaded_at: string;
  file_size: number | null;
}

export interface ProjectStats {
  project_id: number;
  name: string;
  segment_count: number;
  duration_sec: number;
}

export interface StatsResponse {
  total_segments: number;
  total_duration_sec: number;
  total_size_bytes: number;
  avg_duration_sec: number;
  sample_rate_distribution: Record<string, number>;
  format_distribution: Record<string, number>;
  upload_progress: UploadProgress;
  labeling_progress: LabelingProgress;
  recent_uploads: RecentUpload[];
  per_project: ProjectStats[] | null;
}
