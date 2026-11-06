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
const FIELD_LABELS: Record<string, string> = {
  n: '步数',
  name: '名称',
  repeats: '每组重复',
  max_retries: '失败重试',
  concurrency: '并发数',
  per_run_wall_seconds: '单项墙钟上限',
}

const CODE_LABELS: Record<string, string> = {
  spec_invalid: '参数校验失败',
  unknown_model: '模型或版本不存在',
}

/** pydantic 的英文短消息 → 中文；未识别的原样保留（不隐藏信息）。 */
const MESSAGE_PATTERNS: [RegExp, (m: RegExpMatchArray) => string][] = [
  [/^Input should be less than or equal to (\S+)$/, (m) => `不能大于 ${m[1]}`],
  [/^Input should be greater than or equal to (\S+)$/, (m) => `不能小于 ${m[1]}`],
  [/^Input should be greater than (\S+)$/, (m) => `必须大于 ${m[1]}`],
  [/^Input should be less than (\S+)$/, (m) => `必须小于 ${m[1]}`],
  [/^Input should be a valid integer.*/, () => '必须是整数'],
  [/^Input should be a valid number.*/, () => '必须是数字'],
  [/^Field required$/, () => '必填'],
  [/^String should have at least (\d+) characters?$/, (m) => `至少 ${m[1]} 个字符`],
  [/^String should have at most (\d+) characters?$/, (m) => `最多 ${m[1]} 个字符`],
]

/** 应用层 spec 错误（R54）：code 形如 `params.width` / `unknown_model`，
 * message 是 pydantic 的英文短句。能识别的翻译成中文，识别不了返回 null 由调用方回退。 */
function humanizeSpecError(e: SpecError): string | null {
  const field = e.code.startsWith('params.') ? e.code.slice('params.'.length) : e.code
  const label = FIELD_LABELS[field] ?? field
  for (const [re, fmt] of MESSAGE_PATTERNS) {
    const m = e.message.match(re)
    if (m) return `${label ? label + ' ' : ''}${fmt(m)}`
  }
  return null
}

/** 单个 FastAPI 请求体错误 → 中文；识别不了就返回 null，由调用方回退到原文。 */
function humanizeFastApiError(item: FastApiError): string | null {
  const loc = (item.loc ?? []).filter((p) => p !== 'body' && p !== 'query')
  const field = String(loc[loc.length - 1] ?? '')
  const label = FIELD_LABELS[field] ?? field
  const msg = item.msg ?? ''
  for (const [re, fmt] of MESSAGE_PATTERNS) {
    const m = msg.match(re)
    if (m) return `${label ? label + ' ' : ''}${fmt(m)}`
  }
  return null
}

export function errorDetailMessage(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    // 全部可翻译才用中文：一半中文一半英文的横幅比原文更难读，也会丢信息。
    const human = (detail as FastApiError[]).map(humanizeFastApiError)
    if (human.length && human.every((h): h is string => h !== null)) return human.join('；')
    const parts = (detail as FastApiError[])
      .map((item) => {
        const path = (item.loc ?? []).filter((p) => p !== 'body' && p !== 'query').join('.')
        return `${path ? path + ' ' : ''}${item.msg ?? item.type ?? '输入不合法'}`
      })
      .filter(Boolean)
    return parts.length ? `${status}: ${parts.join('; ')}` : `${status}`
  }
  const obj = detail as { code?: string; message?: string; errors?: SpecError[] } | undefined
  const message = (obj?.code ? CODE_LABELS[obj.code] : undefined) ?? obj?.message ?? `${status}`
  if (!obj?.errors?.length) return message
  // 与数组形状同一条规则：全部可识别才译，否则整条回退原文（不混排、不丢诊断）
  const human = obj.errors.map(humanizeSpecError)
  if (human.every((h): h is string => h !== null)) return `${message}：${human.join('；')}`
  return `${message}：${obj.errors.map((e) => `${e.code} ${e.message}`).join('; ')}`
}

/** 404 + 指定路径段才算「该资源已不在」（R50/R51）。
 * 不能只看状态码：删实验、删会话都可能是 404，但清空的应当是各自对应的界面状态。 */
export function isNotFoundOn(e: unknown, pathPart: string): boolean {
  return e instanceof ApiError && e.status === 404 && e.path.includes(pathPart)
}

/** 带状态码与请求路径的错误（R50）：调用方需要区分「会话已回收」与其他失败。 */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly path: string,
    readonly code: string | undefined,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let message = `${res.status}`
    let code: string | undefined
    try {
      const body: unknown = await res.json()
      message = errorDetailMessage(res.status, body)
      const detail = (body as { detail?: unknown } | null)?.detail
      if (detail && !Array.isArray(detail)) code = (detail as { code?: string }).code
    } catch {
      /* keep status code */
    }
    throw new ApiError(res.status, path, code, message)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  listModels: () => request<{ models: ModelInfo[] }>('/api/models'),
  getModel: (id: string, version?: string) =>
    request<ModelInfo>(
      `/api/models/${encodeURIComponent(id)}${version ? `?version=${encodeURIComponent(version)}` : ''}`,
    ),
  getLimits: () => request<LimitsResponse>('/api/limits'),
  createExperiment: (name: string, spec: unknown) =>
    request<{ id: number }>('/api/experiments', { method: 'POST', body: JSON.stringify({ name, spec }) }),
  runExperiment: (id: number, wait: boolean) =>
    request<{ experiment_id: number; run_id: number }>(`/api/experiments/${id}/run`, {
      method: 'POST',
      body: JSON.stringify({ wait }),
    }),
  rerunExperiment: (id: number) =>
    request<{ experiment_id: number; run_id: number; status: string }>(`/api/experiments/${id}/rerun`, {
      method: 'POST',
    }),
  cancelExperiment: (id: number) =>
    request<{ id: number; status: string }>(`/api/experiments/${id}/cancel`, { method: 'POST' }),
  cloneExperiment: (id: number, name?: string) =>
    request<{ id: number }>(`/api/experiments/${id}/clone`, {
      method: 'POST',
      body: JSON.stringify(name ? { name } : {}),
    }),
  getResult: (id: number) => request<ExperimentResult>(`/api/experiments/${id}/result`),
  deleteExperiment: (id: number) => request<void>(`/api/experiments/${id}`, { method: 'DELETE' }),
  getRun: (runId: number, eventsLimit = 50) =>
    request<RunDetail>(`/api/runs/${runId}?events_limit=${eventsLimit}`),
  listExperiments: (limit = 20, offset = 0, modelId?: string, tag?: string) => {
    const q = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    if (modelId) q.set('model_id', modelId)
    if (tag) q.set('tag', tag)
    return request<{
      total: number
      experiments: { id: number; name: string; model_id: string; model_version: string; status: string; tags: string[] }[]
    }>(`/api/experiments?${q.toString()}`)
  },
  setTags: (id: number, tags: string[]) =>
    request<{ id: number; tags: string[] }>(`/api/experiments/${id}/tags`, {
      method: 'PUT',
      body: JSON.stringify({ tags }),
    }),
  createSession: (spec: unknown) =>
    request<SessionState>('/api/sessions', { method: 'POST', body: JSON.stringify({ spec }) }),
  getSession: (id: string) => request<SessionState>(`/api/sessions/${id}`),
  stepSession: (id: string, n: number) =>
    request<SessionState>(`/api/sessions/${id}/step`, { method: 'POST', body: JSON.stringify({ n }) }),
  runSession: (id: string) => request<SessionState>(`/api/sessions/${id}/run`, { method: 'POST' }),
  pauseSession: (id: string) => request<SessionState>(`/api/sessions/${id}/pause`, { method: 'POST' }),
  resumeSession: (id: string) => request<SessionState>(`/api/sessions/${id}/resume`, { method: 'POST' }),
  resetSession: (id: string) => request<SessionState>(`/api/sessions/${id}/reset`, { method: 'POST' }),
  checkpointSession: (id: string) =>
    request<{ session_id: string; checkpoint: Record<string, unknown> }>(`/api/sessions/${id}/checkpoint`, {
      method: 'POST',
    }),
  restoreSession: (id: string, checkpoint: Record<string, unknown>) =>
    request<SessionState>(`/api/sessions/${id}/restore`, {
      method: 'POST',
      body: JSON.stringify({ checkpoint }),
    }),
  createBatch: (body: {
    name: string
    spec: unknown
    grid: Record<string, unknown[]>
    repeats: number
    seed_strategy: string
    max_retries: number
    per_run_wall_seconds: number
  }) => request<BatchDetail>('/api/batches', { method: 'POST', body: JSON.stringify(body) }),
  listBatches: (limit = 10, offset = 0) =>
    request<{ total: number; batches: BatchListItem[] }>(`/api/batches?limit=${limit}&offset=${offset}`),
  getBatch: (id: number) => request<BatchDetail>(`/api/batches/${id}`),
  getBatchFindings: (id: number) => request<FindingsResponse>(`/api/batches/${id}/findings`),
  listBatchItems: (id: number, limit = 50, offset = 0) =>
    request<{ total: number; items: BatchItem[] }>(
      `/api/batches/${id}/items?limit=${limit}&offset=${offset}`,
    ),
  cancelBatch: (id: number) =>
    request<BatchDetail>(`/api/batches/${id}/cancel`, { method: 'POST' }),
  deleteBatch: (id: number) => request<void>(`/api/batches/${id}`, { method: 'DELETE' }),
  reportUrl: (id: number, format: 'markdown' | 'json') =>
    `/api/experiments/${id}/report?format=${format}`,
  batchCsvUrl: (id: number) => `/api/batches/${id}/export.csv`,
  batchReportUrl: (id: number, format: 'markdown' | 'json') =>
    `/api/batches/${id}/report?format=${format}`,
}
