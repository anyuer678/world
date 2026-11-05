import type {
  BatchDetail,
  BatchItem,
  BatchListItem,
  ExperimentResult,
  LimitsResponse,
  ModelInfo,
  RunDetail,
  SessionState,
} from './types'
import type { FindingsResponse } from './findings'

type SpecError = { code: string; message: string }
type FastApiError = { loc?: unknown[]; msg?: string; type?: string }

/**
 * Errors reach us in two shapes: the app's spec validation returns
 * `detail: {code, message, errors[]}` while FastAPI's own request-body rules
 * return `detail: [{loc, msg, type}]`. Reading only the first shape made every
 * body-rule violation render as a bare "422" with no reason.
 */
export function errorDetailMessage(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const parts = (detail as FastApiError[])
      .map((item) => {
        const path = (item.loc ?? []).filter((p) => p !== 'body' && p !== 'query').join('.')
        return `${path ? path + ' ' : ''}${item.msg ?? item.type ?? '输入不合法'}`
      })
      .filter(Boolean)
    return parts.length ? `${status}: ${parts.join('; ')}` : `${status}`
  }
  const obj = detail as { message?: string; errors?: SpecError[] } | undefined
  const message = obj?.message ?? `${status}`
  return obj?.errors?.length ? `${message}: ${obj.errors.map((e) => `${e.code} ${e.message}`).join('; ')}` : message
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let message = `${res.status}`
    try {
      message = errorDetailMessage(res.status, await res.json())
    } catch {
      /* keep status code */
    }
    throw new Error(message)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  listModels: () => request<{ models: ModelInfo[] }>('/api/models'),
  getLimits: () => request<LimitsResponse>('/api/limits'),
  createExperiment: (name: string, spec: unknown) =>
    request<{ id: number }>('/api/experiments', { method: 'POST', body: JSON.stringify({ name, spec }) }),
  runExperiment: (id: number, wait: boolean) =>
    request<{ experiment_id: number; run_id: number }>(`/api/experiments/${id}/run`, {
      method: 'POST',
      body: JSON.stringify({ wait }),
    }),
  getResult: (id: number) => request<ExperimentResult>(`/api/experiments/${id}/result`),
  getRun: (runId: number) => request<RunDetail>(`/api/runs/${runId}`),
  listExperiments: () =>
    request<{ total: number; experiments: { id: number; name: string; status: string; model_id: string }[] }>(
      '/api/experiments?limit=20',
    ),
  createSession: (spec: unknown) =>
    request<SessionState>('/api/sessions', { method: 'POST', body: JSON.stringify({ spec }) }),
  getSession: (id: string) => request<SessionState>(`/api/sessions/${id}`),
  stepSession: (id: string, n: number) =>
    request<SessionState>(`/api/sessions/${id}/step`, { method: 'POST', body: JSON.stringify({ n }) }),
  runSession: (id: string) => request<SessionState>(`/api/sessions/${id}/run`, { method: 'POST' }),
  pauseSession: (id: string) => request<SessionState>(`/api/sessions/${id}/pause`, { method: 'POST' }),
  resumeSession: (id: string) => request<SessionState>(`/api/sessions/${id}/resume`, { method: 'POST' }),
  resetSession: (id: string) => request<SessionState>(`/api/sessions/${id}/reset`, { method: 'POST' }),
  createBatch: (body: {
    name: string
    spec: unknown
    grid: Record<string, unknown[]>
    repeats: number
    seed_strategy: string
    max_retries: number
    per_run_wall_seconds: number
  }) => request<BatchDetail>('/api/batches', { method: 'POST', body: JSON.stringify(body) }),
  listBatches: () =>
    request<{ total: number; batches: BatchListItem[] }>('/api/batches?limit=10'),
  getBatch: (id: number) => request<BatchDetail>(`/api/batches/${id}`),
  getBatchFindings: (id: number) => request<FindingsResponse>(`/api/batches/${id}/findings`),
  listBatchItems: (id: number, limit = 50) =>
    request<{ total: number; items: BatchItem[] }>(`/api/batches/${id}/items?limit=${limit}`),
  cancelBatch: (id: number) =>
    request<BatchDetail>(`/api/batches/${id}/cancel`, { method: 'POST' }),
  reportUrl: (id: number, format: 'markdown' | 'json') =>
    `/api/experiments/${id}/report?format=${format}`,
  batchCsvUrl: (id: number) => `/api/batches/${id}/export.csv`,
}
