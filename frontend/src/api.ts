import type {
  BatchDetail,
  BatchItem,
  BatchListItem,
  ExperimentResult,
  ModelInfo,
  RunDetail,
  SessionState,
} from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let message = `${res.status}`
    try {
      const body = await res.json()
      const detail = body.detail
      message = typeof detail === 'string' ? detail : detail?.message ?? message
      if (detail?.errors?.length) {
        message += ': ' + detail.errors.map((e: { code: string; message: string }) => `${e.code} ${e.message}`).join('; ')
      }
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
  listBatchItems: (id: number, limit = 50) =>
    request<{ total: number; items: BatchItem[] }>(`/api/batches/${id}/items?limit=${limit}`),
  cancelBatch: (id: number) =>
    request<BatchDetail>(`/api/batches/${id}/cancel`, { method: 'POST' }),
  reportUrl: (id: number, format: 'markdown' | 'json') =>
    `/api/experiments/${id}/report?format=${format}`,
  batchCsvUrl: (id: number) => `/api/batches/${id}/export.csv`,
}
