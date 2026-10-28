import type { Series } from './chartRender'
import type { BatchSummary } from './types'

export interface SweepSelection {
  param: string
  metric: string
  others: Record<string, unknown>
  series: Series
}

function isNum(v: unknown): boolean {
  return typeof v === 'number' && Number.isFinite(v)
}

function numericParams(grid: Record<string, unknown[]>): string[] {
  return Object.entries(grid)
    .filter(([, vals]) => vals.length > 0 && vals.every(isNum))
    .map(([k]) => k)
}

function modalSlice(
  combos: BatchSummary['combos'],
  numeric: string[],
  param: string,
): BatchSummary['combos'] {
  const others = numeric.filter((p) => p !== param)
  const base: Record<string, unknown> = {}
  for (const p of others) {
    const counts = new Map<unknown, number>()
    for (const c of combos) {
      const v = c.params[p]
      counts.set(v, (counts.get(v) ?? 0) + 1)
    }
    let best: unknown
    let n = -1
    for (const [v, k] of counts) {
      if (k > n) {
        best = v
        n = k
      }
    }
    base[p] = best
  }
  return combos.filter((c) => others.every((p) => c.params[p] === base[p]))
}

function eligibleParams(combos: BatchSummary['combos'], grid: Record<string, unknown[]>): string[] {
  const numeric = numericParams(grid)
  return numeric.filter(
    (param) => new Set(modalSlice(combos, numeric, param).map((c) => c.params[param])).size >= 3,
  )
}

function metricsFor(combos: BatchSummary['combos'], param: string): string[] {
  const names = new Set<string>()
  for (const c of combos) {
    if (param in c.params) for (const m of Object.keys(c.metrics)) names.add(m)
  }
  return [...names].sort()
}

export function sweepParamOptions(
  summary: BatchSummary | undefined,
  grid: Record<string, unknown[]>,
): string[] {
  if (!summary) return []
  return eligibleParams(summary.combos, grid)
}

export function sweepMetricOptions(
  summary: BatchSummary | undefined,
  param: string,
): string[] {
  if (!summary) return []
  return metricsFor(summary.combos, param)
}

export function buildSweep(
  summary: BatchSummary | undefined,
  grid: Record<string, unknown[]>,
  param: string,
  metric: string,
): SweepSelection | null {
  if (!summary) return null
  const numeric = numericParams(grid)
  const slice = modalSlice(summary.combos, numeric, param)
  const points = slice
    .filter((c) => c.params[param] !== undefined && (c.metrics[metric]?.n ?? 0) > 0)
    .map((c) => [c.params[param] as number, c.metrics[metric].mean] as [number, number])
    .sort((a, b) => a[0] - b[0])
  if (points.length < 2) return null
  const others: Record<string, unknown> = {}
  for (const p of numeric) {
    if (p === param) continue
    const vals = slice.map((c) => c.params[p])
    if (new Set(vals).size === 1) others[p] = vals[0]
  }
  return {
    param,
    metric,
    others,
    series: { name: metric, color: '#2563eb', data: points },
  }
}

export function defaultSweepSelection(
  summary: BatchSummary | undefined,
  grid: Record<string, unknown[]>,
  findings?: { type: string; param?: string; metric: string }[],
): SweepSelection | null {
  if (!summary) return null
  const params = eligibleParams(summary.combos, grid)
  if (params.length === 0) return null
  const param = params[0]
  const metrics = metricsFor(summary.combos, param)
  if (metrics.length === 0) return null
  const hit = findings?.find((f) => f.type === 'jump' && f.param === param)
  const metric = hit && metrics.includes(hit.metric) ? hit.metric : metrics[0]
  return buildSweep(summary, grid, param, metric)
}
