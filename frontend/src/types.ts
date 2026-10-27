export interface ModelInfo {
  model_id: string
  version: string
  display_name: string
  description: string
  model_type: 'time_stepped' | 'discrete_event'
  params_schema: Record<string, unknown>
  visualizer: { kind: string; series?: string[] }
  example_spec: ModelSpec
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
