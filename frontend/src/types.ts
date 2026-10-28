export interface ScenarioInfo {
  id: string
  title: string
  description: string
  params: Record<string, unknown>
  seed: number
  stop_condition: { type: 'steps' | 'sim_time' | 'until_empty'; value?: number }
}

export interface ModelInfo {
  model_id: string
  version: string
  display_name: string
  description: string
  model_type: 'time_stepped' | 'discrete_event'
  params_schema: Record<string, unknown>
  visualizer: { kind: string; series?: string[] }
  example_spec: ModelSpec
  scenarios: ScenarioInfo[]
}

export interface ModelSpec {
  schema_version?: number
  model_id: string
  model_version?: string | null
  params: Record<string, unknown>
  stop_condition: { type: 'steps' | 'sim_time' | 'until_empty'; value?: number }
  seed?: number | null
}

export interface Experiment {
  id: number
  name: string
  model_id: string
  model_version: string
  status: string
  seed: number | null
  tags: string[]
  created_at: string
  duration_ms: number | null
  error: string | null
  spec: ModelSpec
  runs: RunSummary[]
}

export interface RunSummary {
  id: number
  repeat_index: number
  seed: number
  status: string
  steps: number | null
  sim_time: number | null
  duration_ms: number | null
  result_sha256: string | null
  error: string | null
}

export interface EventRecord {
  seq: number
  time: number
  kind: string
  message: string
  data: Record<string, unknown>
}

export interface RunDetail extends RunSummary {
  metrics: Record<string, number> | null
  summary: Record<string, unknown> | null
  events: EventRecord[]
}

export interface ExperimentResult {
  experiment: Experiment
  runs: (RunSummary & { metrics: Record<string, number> | null; summary: Record<string, unknown> | null })[]
  aggregate: Record<string, number> | null
}

export interface SessionSnapshot {
  step: number
  time: number
  status: string
  state: Record<string, unknown>
  metrics: Record<string, number>
}

export interface SessionState {
  session_id: string
  status: 'idle' | 'running' | 'paused' | 'completed' | 'cancelled' | 'error' | 'step_limit' | 'wall_timeout'
  stop_reason: string | null
  error: string | null
  model_id: string
  model_version: string
  model_type: string
  visualizer: { kind: string; series?: string[] }
  display_name: string
  spec: ModelSpec
  snapshot: SessionSnapshot
  events: EventRecord[]
  chunk_steps: number
}

export interface MetricStats {
  n: number
  mean: number
  std: number
  p50: number
  p90: number
  ci95_low: number
  ci95_high: number
}

export interface BatchSummary {
  combos: { params: Record<string, unknown>; n: number; metrics: Record<string, MetricStats> }[]
  sensitivity: { param: string; metric: string; pearson_r: number; n_combos: number }[]
  sensitivity_note: string
  ci_note: string
}

export interface BatchDetail {
  id: number
  name: string
  model_id: string
  model_version: string
  status: string
  total_items: number
  repeats: number
  seed_strategy: string
  seed_base: number | null
  created_at: string | null
  duration_ms: number | null
  error: string | null
  counts: Record<string, number>
  spec: ModelSpec
  grid: Record<string, unknown[]>
  summary?: BatchSummary
}

export interface BatchListItem {
  id: number
  name: string
  model_id: string
  model_version: string
  status: string
  total_items: number
  done_items: number
  created_at: string
}

export interface BatchItem {
  id: number
  item_index: number
  params: Record<string, unknown>
  repeat_index: number
  seed: number
  status: string
  attempts: number
  steps: number | null
  sim_time: number | null
  metrics: Record<string, number> | null
  result_sha256: string | null
  error: string | null
  duration_ms: number | null
}
