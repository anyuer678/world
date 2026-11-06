import { describe, it, expect } from 'vitest'
import { historyHeading, historyMoreLabel, isSessionGone, modelTypeLabel, quickPicks, scenarioSpec, stepProblem, versionOptions } from './App'
import { statusLabel } from './labels'
import { formatValue } from './SimView'
import { parseValues } from './BatchPanel'
import { parseArrayText, resolve } from './ParamForm'
import { summarizeMetrics } from './summary'
import { formatFinding } from './findings'
import { FALLBACK_LIMITS, batchSubmitProblem, batchesHeading, itemsHeading } from './BatchPanel'
import { toggleCompare } from './ComparePanel'
import { ApiError, errorDetailMessage, isNotFoundOn } from './api'

describe('batchSubmitProblem (server-provided limits, R29/R30)', () => {
  it('rejects repeats above the server max that the old frontend ignored', () => {
    expect(batchSubmitProblem(FALLBACK_LIMITS, { name: 'b', totalItems: 150, repeats: 150, retries: 0 })).toContain(
      '每组重复需在 1–100 之间',
    )
    expect(batchSubmitProblem(FALLBACK_LIMITS, { name: 'b', totalItems: 0, repeats: 0, retries: 0 })).toContain(
      '每组重复需在 1–100 之间',
    )
  })

  it('rejects over-cap grids, blank and overlong names; accepts a sane batch', () => {
    expect(batchSubmitProblem(FALLBACK_LIMITS, { name: 'b', totalItems: 2001, repeats: 3, retries: 0 })).toContain(
      '总项数 2001 超过上限 2000',
    )
    expect(batchSubmitProblem(FALLBACK_LIMITS, { name: '   ', totalItems: 3, repeats: 3, retries: 0 })).toBe(
      '批量名称不能为空',
    )
    expect(
      batchSubmitProblem(FALLBACK_LIMITS, { name: 'x'.repeat(201), totalItems: 3, repeats: 3, retries: 0 }),
    ).toContain('批量名称最长 200 字符')
    expect(batchSubmitProblem(FALLBACK_LIMITS, { name: 'ok', totalItems: 60, repeats: 3, retries: 0 })).toBeNull()
  })

  it('rejects retries outside the server window (R30: free-text field used to reach a bare 422)', () => {
    expect(batchSubmitProblem(FALLBACK_LIMITS, { name: 'b', totalItems: 3, repeats: 3, retries: 11 })).toContain(
      '失败重试需在 0–10 之间（当前 11）',
    )
    expect(
      batchSubmitProblem(
        { ...FALLBACK_LIMITS, retriesMax: 5 },
        { name: 'b', totalItems: 3, repeats: 3, retries: 6 },
      ),
    ).toContain('失败重试需在 0–5 之间')
    expect(batchSubmitProblem(FALLBACK_LIMITS, { name: 'b', totalItems: 3, repeats: 3, retries: 10 })).toBeNull()
  })
})

describe('itemsHeading (R34：单项结果表头必须交代总数)', () => {
  it('shows the total when the table only holds the first page', () => {
    expect(itemsHeading(50, 1200)).toBe('单项结果（显示前 50 / 共 1200 项，其余见「导出 CSV」）')
  })
  it('says 全部 when nothing is hidden', () => {
    expect(itemsHeading(8, 8)).toBe('单项结果（全部 8 项）')
    expect(itemsHeading(3, 0)).toBe('单项结果（全部 3 项）')  // total 未知时不谎报有隐藏项
  })
})

describe('errorDetailMessage (two 422 shapes, R30)', () => {
  it('reads the app-level spec validation object shape', () => {
    expect(
      errorDetailMessage(422, {
        detail: { code: 'spec_invalid', message: 'spec validation failed', errors: [{ code: 'params.gamma', message: '≥0' }] },
      }),
    ).toBe('参数校验失败：params.gamma ≥0')
  })

  it('reads FastAPI request-body rule arrays instead of rendering a bare 422', () => {
    expect(
      errorDetailMessage(422, {
        detail: [{ type: 'less_than_equal', loc: ['body', 'repeats'], msg: 'Input should be less than or equal to 100', input: 150 }],
      }),
    ).toBe('每组重复 不能大于 100')
    // 有一条识别不了就整条回退（不混排中英、不丢信息）
    expect(
      errorDetailMessage(422, {
        detail: [
          { loc: ['body', 'grid'], msg: 'Field required' },
          { loc: ['query', 'x'], msg: 'Bad x' },
        ],
      }),
    ).toBe('422: grid Field required; x Bad x')
  })

  it('translates nested spec param messages and strips the params. prefix (R54)', () => {
    expect(
      errorDetailMessage(422, {
        detail: {
          code: 'spec_invalid',
          message: 'spec validation failed',
          errors: [{ code: 'params.width', message: 'Input should be greater than or equal to 5' }],
        },
      }),
    ).toBe('参数校验失败：width 不能小于 5')
    // 认不出的嵌套消息整条回退（保留 code 与原文）
    expect(
      errorDetailMessage(422, {
        detail: { code: 'spec_invalid', message: 'spec validation failed', errors: [{ code: 'params.gamma', message: '≥0' }] },
      }),
    ).toBe('参数校验失败：params.gamma ≥0')
  })

  it('translates the session step bound and keeps unknown messages verbatim', () => {
    expect(
      errorDetailMessage(422, {
        detail: [{ type: 'less_than_equal', loc: ['body', 'n'], msg: 'Input should be less than or equal to 1000000' }],
      }),
    ).toBe('步数 不能大于 1000000')
    expect(
      errorDetailMessage(422, { detail: [{ type: 'missing', loc: ['body', 'name'], msg: 'Field required' }] }),
    ).toBe('名称 必填')
    expect(
      errorDetailMessage(422, { detail: [{ type: 'custom', loc: ['body', 'repeats'], msg: 'Something odd' }] }),
    ).toBe('422: repeats Something odd')
  })

  it('falls back to plain strings and bare status codes', () => {
    expect(errorDetailMessage(404, { detail: 'run 9 not found' })).toBe('run 9 not found')
    expect(errorDetailMessage(500, {})).toBe('500')
    expect(errorDetailMessage(422, { detail: [] })).toBe('422')
    expect(errorDetailMessage(400, null)).toBe('400')
  })
})
import { buildSweep, defaultSweepSelection, sweepParamOptions } from './sweepChart'
import { computeBounds, edgeCells, parseNetwork } from './trafficRender'
import { fmtTick, ganttExtent, ganttRows, niceMax, runsFromBits, seriesBounds } from './chartRender'
import type { JSONSchema } from './schema'
import type { BatchSummary, ModelInfo, ScenarioInfo } from './types'

describe('trafficRender', () => {
  const net = {
    nodes: [
      { id: 'a', x: 0, y: 0 },
      { id: 'b', x: 30, y: 40 },
    ],
    edges: [{ src: 'a', dst: 'b' }],
  }

  it('parses a valid network object', () => {
    expect(parseNetwork(net)).toEqual(net)
  })

  it('rejects malformed payloads', () => {
    expect(parseNetwork(null)).toBeNull()
    expect(parseNetwork({})).toBeNull()
    expect(parseNetwork({ nodes: 'x', edges: [] })).toBeNull()
  })

  it('derives edge cell counts from euclidean distance', () => {
    expect(edgeCells(net, net.edges[0])).toBe(50)
    expect(edgeCells(net, { src: 'a', dst: 'zz' })).toBe(1)
  })

  it('computes bounds and degrades degenerate extents', () => {
    expect(computeBounds(net)).toEqual({ minX: 0, minY: 0, maxX: 30, maxY: 40 })
    const point = { nodes: [{ id: 'a', x: 5, y: 5 }], edges: [] }
    const b = computeBounds(point)
    expect(b.maxX - b.minX).toBeGreaterThan(0)
    expect(b.maxY - b.minY).toBeGreaterThan(0)
  })
})

describe('statusLabel', () => {
  it('maps known session statuses to Chinese labels', () => {
    expect(statusLabel('idle')).toBe('就绪')
    expect(statusLabel('running')).toBe('运行中')
    expect(statusLabel('paused')).toBe('已暂停')
    expect(statusLabel('completed')).toBe('已完成')
    expect(statusLabel('cancelled')).toBe('已取消')
    expect(statusLabel('error')).toBe('出错')
    expect(statusLabel('step_limit')).toBe('达步数上限')
    expect(statusLabel('wall_timeout')).toBe('超时')
    expect(statusLabel('queued')).toBe('排队中')
    expect(statusLabel('pending')).toBe('等待中')
    expect(statusLabel('failed')).toBe('失败')
    expect(statusLabel('created')).toBe('已创建')
  })

  it('passes unknown statuses through unchanged', () => {
    expect(statusLabel('mystery')).toBe('mystery')
  })
})

describe('formatValue', () => {
  it('formats integers without decimals', () => {
    expect(formatValue(42)).toBe('42')
  })

  it('formats floats with 4 decimal places', () => {
    expect(formatValue(3.14159265)).toBe('3.1416')
  })

  it('summarizes arrays by length only', () => {
    expect(formatValue([1, 2, 3])).toBe('[3 项]')
  })

  it('truncates object JSON to 80 chars', () => {
    const big = { blob: 'x'.repeat(200) }
    const out = formatValue(big)
    expect(out.startsWith('{"blob":"')).toBe(true)
    expect(out.length).toBeLessThanOrEqual(80)
  })

  it('renders strings and null as-is', () => {
    expect(formatValue('fcfs')).toBe('fcfs')
    expect(formatValue(null)).toBe('null')
  })
})

describe('parseValues', () => {
  it('converts numeric tokens to numbers and keeps the rest as strings', () => {
    expect(parseValues('1, 2.5 fifo -3e2')).toEqual([1, 2.5, 'fifo', -300])
  })

  it('splits on commas and whitespace', () => {
    expect(parseValues('10,20 30')).toEqual([10, 20, 30])
  })

  it('returns empty list for empty input', () => {
    expect(parseValues('')).toEqual([])
    expect(parseValues('   ')).toEqual([])
  })

  it('treats lone dots and parameter-like tokens as strings', () => {
    expect(parseValues('. rr')).toEqual(['.', 'rr'])
  })
})

describe('resolve (param schema ref resolution)', () => {
  const root: JSONSchema = {
    $defs: {
      bounded: { type: 'integer', minimum: 1, maximum: 64 },
    },
    properties: {},
  }

  it('resolves $ref into $defs', () => {
    expect(resolve(root, { $ref: '#/$defs/bounded' })).toEqual(root.$defs!.bounded)
  })

  it('collapses anyOf [T, null] to T with nullable flag', () => {
    const out = resolve(root, {
      anyOf: [{ type: 'number', minimum: 0 }, { type: 'null' }],
    })
    expect(out).toEqual({ type: 'number', minimum: 0, nullable: true })
  })

  it('keeps outer title and description when collapsing anyOf', () => {
    const out = resolve(root, {
      title: '指定初始图案',
      description: '给出 0/1 矩阵',
      anyOf: [{ type: 'array', items: { type: 'array' } }, { type: 'null' }],
    })
    expect(out).toEqual({
      type: 'array',
      items: { type: 'array' },
      nullable: true,
      title: '指定初始图案',
      description: '给出 0/1 矩阵',
    })
  })

  it('unwraps allOf to its first branch', () => {
    expect(resolve(root, { allOf: [{ type: 'boolean' }, { title: 'x' }] })).toEqual({ type: 'boolean' })
  })

  it('returns plain schemas untouched', () => {
    const s: JSONSchema = { type: 'string', enum: ['fcfs', 'sjf'] }
    expect(resolve(root, s)).toEqual(s)
  })
})

describe('modelTypeLabel', () => {
  it('translates both model types and passes others through', () => {
    expect(modelTypeLabel('discrete_event')).toBe('离散事件')
    expect(modelTypeLabel('time_stepped')).toBe('时间步进')
    expect(modelTypeLabel('other')).toBe('other')
  })
})

describe('scenarioSpec', () => {
  const scenario: ScenarioInfo = {
    id: 'rush-hour',
    title: '高峰期为什么突然堵死',
    description: '……',
    params: { servers: 1 },
    seed: 7,
    stop_condition: { type: 'steps', value: 30000 },
  }

  it('builds a complete spec from a scenario without mutating it', () => {
    const spec = scenarioSpec('queueing', scenario)
    expect(spec).toEqual({
      schema_version: 1,
      model_id: 'queueing',
      params: { servers: 1 },
      stop_condition: { type: 'steps', value: 30000 },
      seed: 7,
    })
    spec.params.servers = 99
    expect(scenario.params.servers).toBe(1)
  })

  it('normalizes scenarios that omit seed/stop_condition via current-form fallback', () => {
    const bare: ScenarioInfo = { id: 'a', title: 'A', description: 'd', params: { n: 1 } }
    const withCurrent = scenarioSpec('plug', bare, {
      stop_condition: { type: 'sim_time', value: 5 },
      seed: 42,
    })
    expect(withCurrent.stop_condition).toEqual({ type: 'sim_time', value: 5 })
    expect(withCurrent.seed).toBe(42)
    const defaulted = scenarioSpec('plug', bare)
    expect(defaulted.stop_condition).toEqual({ type: 'steps', value: 1000 })
    expect(defaulted.seed).toBeNull()
  })

  it('carries an explicit model_version and omits it when unset', () => {
    const bare: ScenarioInfo = { id: 'a', title: 'A', description: 'd', params: { n: 1 } }
    const versioned = scenarioSpec('plug', bare, {
      stop_condition: { type: 'steps', value: 10 },
      seed: 1,
      model_version: '2.0.0',
    })
    expect(versioned.model_version).toBe('2.0.0')
    expect(scenarioSpec('plug', bare, { stop_condition: { type: 'steps', value: 10 }, seed: 1, model_version: null })).not.toHaveProperty('model_version')
  })
})

describe('versionOptions', () => {
  it('keeps catalog order and appends the latest version only when missing', () => {
    expect(versionOptions(['1.0.0', '2.0.0'], '2.0.0')).toEqual(['1.0.0', '2.0.0'])
    expect(versionOptions(['1.0.0'], '2.0.0')).toEqual(['2.0.0', '1.0.0'])
    expect(versionOptions([], '1.0.0')).toEqual(['1.0.0'])
  })
})

describe('summarizeMetrics', () => {
  it('judges queue load by utilization and reports drops', () => {
    const high = summarizeMetrics('queue', {
      utilization: 0.9039,
      avg_waiting_time: 9.59,
      avg_response_time: 10.58,
      drop_rate: 0,
    })
    expect(high[0]).toContain('90.4%')
    expect(high[0]).toContain('极限')
    expect(high[1]).toContain('9.59')
    expect(high.some((s) => s.includes('丢弃'))).toBe(false)

    const drop = summarizeMetrics('queue', { utilization: 1.5, avg_waiting_time: 3, drop_rate: 0.21 })
    expect(drop.some((s) => s.includes('21.0%') && s.includes('拒之门外'))).toBe(true)
  })

  it('summarizes cache hit quality', () => {
    const out = summarizeMetrics('cache', { hit_rate: 0.5004, avg_cost_per_access: 5.5 })
    expect(out[0]).toContain('50.0%')
    expect(out[0]).toContain('一定作用')
    expect(out[1]).toContain('5.50')
  })

  it('judges schelling settlement and segregation level', () => {
    const zero = summarizeMetrics('schelling', { moves_total: 0, unhappy_rate: 0, segregation_index: 0.503 })
    expect(zero[0]).toContain('保持混居')
    const settled = summarizeMetrics('schelling', { moves_total: 382, unhappy_rate: 0, segregation_index: 0.729 })
    expect(settled.some((s) => s.includes('都已安顿') && s.includes('0.73'))).toBe(true)
    const churning = summarizeMetrics('schelling', { moves_total: 12202, unhappy_rate: 0.25, segregation_index: 0.994 })
    expect(churning.some((s) => s.includes('动荡') && s.includes('分区清晰'))).toBe(true)
    expect(summarizeMetrics('schelling', {})).toEqual([])
  })

  it('summarizes cellular automaton population trend', () => {
    const peak = summarizeMetrics('ca', {
      generation: 300,
      population: 380,
      population_max: 400,
      population_min: 100,
      births_total: 2000,
      deaths_total: 1620,
    })
    expect(peak[0]).toContain('300')
    expect(peak[0]).toContain('峰值')
    const shrunk = summarizeMetrics('ca', {
      generation: 300,
      population: 40,
      population_max: 400,
      births_total: 2000,
      deaths_total: 1960,
    })
    expect(shrunk[0]).toContain('萎缩')
  })

  it('summarizes SIR outbreak severity and peak', () => {
    const big = summarizeMetrics('sir', {
      tick: 120,
      population: 10000,
      attack_rate: 0.893,
      peak_infected: 4150,
      peak_time: 34.0,
    })
    expect(big[0]).toContain('89.3%')
    expect(big[0]).toContain('大流行')
    expect(big[1]).toContain('4150')
    expect(big[1]).toContain('第 34 天')
    const out = summarizeMetrics('sir', { population: 10000, attack_rate: 0.0009, peak_infected: 10 })
    expect(out[0]).toContain('熄灭')
  })

  it('summarizes traffic congestion by completion ratio', () => {
    const jam = summarizeMetrics('traffic', {
      spawned: 698,
      completed: 300,
      avg_travel_time: 52.74,
      avg_wait_ticks: 25.47,
    })
    expect(jam[0]).toContain('698')
    expect(jam[0]).toContain('滞留')
    expect(jam[1]).toContain('25.47')
    const clear = summarizeMetrics('traffic', { spawned: 100, completed: 95 })
    expect(clear[0]).toContain('畅通')
  })

  it('summarizes predator-prey cycles vs stable coexistence', () => {
    const cycling = summarizeMetrics('predator_prey', {
      prey_peaks: 8,
      cycle_period: 11.0,
      distance_to_equilibrium: 0.62,
      prey_min: 0.8,
      prey_max: 12.4,
      predator_min: 0.9,
      predator_max: 6.1,
    })
    expect(cycling[0]).toContain('8 次')
    expect(cycling[1]).toContain('兴衰循环')
    expect(cycling[1]).toContain('12.40')
    const settled = summarizeMetrics('predator_prey', {
      prey_peaks: 3,
      cycle_period: 9.5,
      distance_to_equilibrium: 0.001,
      equilibrium_prey: 5.0,
      equilibrium_predator: 0.9375,
    })
    expect(settled[1]).toContain('收敛到平衡点')
    expect(settled[1]).toContain('稳定共存')
  })

  it('summarizes cpu scheduling and unknown kinds yield nothing', () => {
    const out = summarizeMetrics('cpu_schedule', {
      avg_waiting_time: 2.5,
      avg_turnaround_time: 4.2,
      cpu_utilization: 0.87,
      arrived: 200,
      completed: 150,
    })
    expect(out[0]).toContain('2.50')
    expect(out.some((s) => s.includes('87.0%'))).toBe(true)
    expect(out.some((s) => s.includes('50 个未完成'))).toBe(true)
    expect(summarizeMetrics('mystery_kind', { a: 1 })).toEqual([])
    expect(summarizeMetrics('queue', {})).toEqual([])
  })
})

describe('quickPicks', () => {
  const mkModel = (id: string, scenarioIds: string[]): ModelInfo => ({
    model_id: id,
    version: '1.0.0',
    versions: ['1.0.0'],
    display_name: id,
    description: '',
    model_type: 'time_stepped',
    params_schema: {},
    visualizer: { kind: id },
    example_spec: { model_id: id, params: {}, stop_condition: { type: 'steps', value: 1 } },
    scenarios: scenarioIds.map(
      (sid): ScenarioInfo => ({
        id: sid,
        title: `${id}:${sid}`,
        description: '',
        params: {},
        seed: 1,
        stop_condition: { type: 'steps', value: 1 },
      }),
    ),
  })

  it('resolves curated picks in order when present', () => {
    const models = [
      mkModel('queueing', ['rush-hour', 'other']),
      mkModel('cellular_automaton', ['game-of-life']),
      mkModel('traffic_network', ['no-signal']),
      mkModel('schelling', ['mild-preference']),
      mkModel('sir', ['outbreak']),
      mkModel('predator_prey', ['neutral-cycles']),
      mkModel('cpu_scheduling', ['rr-quantum-too-small']),
      mkModel('cache_sim', ['zipf-hit-ceiling']),
      mkModel('sandpile', ['sandpile-critical']),
    ]
    expect(quickPicks(models).map((p) => p.model.model_id)).toEqual([
      'schelling',
      'cellular_automaton',
      'queueing',
      'traffic_network',
      'sir',
      'predator_prey',
      'cpu_scheduling',
      'cache_sim',
      'sandpile',
    ])
    expect(quickPicks(models)[0].scenario.id).toBe('mild-preference')
  })

  it('skips missing models or scenarios instead of throwing', () => {
    expect(quickPicks([])).toEqual([])
    expect(quickPicks([mkModel('queueing', ['nope'])])).toEqual([])
  })
})

describe('findings', () => {
  it('formats jump findings with direction and factor', () => {
    const up = formatFinding({
      type: 'jump', param: 'load', from: 0.8, to: 0.9, metric: 'avg_waiting_time',
      value_from: 2.6, value_to: 26, ratio: 10,
    })
    expect(up).toContain('跳升')
    expect(up).toContain('10 倍')
    expect(up).toContain('临界点')
    const down = formatFinding({
      type: 'jump', param: 'x', from: 1, to: 2, metric: 'm',
      value_from: 30, value_to: 3, ratio: 10,
    })
    expect(down).toContain('坍缩')
  })

  it('formats collapse-to-zero jumps without a factor', () => {
    const gone = formatFinding({
      type: 'jump', param: 'servers', from: 1, to: 2, metric: 'final_queue_length',
      value_from: 9311, value_to: 0, ratio: null,
    })
    expect(gone).toContain('完全消失')
    expect(gone).toContain('9311')
    expect(gone).toContain('临界点')
    expect(gone).not.toContain('倍')
    const born = formatFinding({
      type: 'jump', param: 'load', from: 0.8, to: 0.9, metric: 'm',
      value_from: 0, value_to: 12, ratio: null,
    })
    expect(born).toContain('从无到有')
    expect(born).not.toContain('坍缩')
  })

  it('formats dispersion findings with cv and params', () => {
    const s = formatFinding({
      type: 'dispersion', params: { load: 0.5 }, metric: 'm', cv: 0.8, n: 4, mean: 1, std: 0.8,
    })
    expect(s).toContain('80%')
    expect(s).toContain('load=0.5')
    expect(s).toContain('重复次数')
  })

  it('drops the location clause for dispersion findings without grid params', () => {
    const s = formatFinding({
      type: 'dispersion', params: {}, metric: 'm', cv: 0.8, n: 4, mean: 1, std: 0.8,
    })
    expect(s).not.toContain('在')
    expect(s).not.toContain('处')
    expect(s).toContain('指标 m 重复间波动很大')
  })
})

describe('sweepChart', () => {
  const grid = { servers: [1, 2, 4], load: [0.5, 0.9] }
  const combos: BatchSummary['combos'] = [
    { params: { servers: 1, load: 0.5 }, n: 2, metrics: { m: { n: 2, mean: 100, std: 0, p50: 100, p90: 100, ci95_low: 100, ci95_high: 100 } } },
    { params: { servers: 2, load: 0.5 }, n: 2, metrics: { m: { n: 2, mean: 10, std: 0, p50: 10, p90: 10, ci95_low: 10, ci95_high: 10 } } },
    { params: { servers: 4, load: 0.5 }, n: 2, metrics: { m: { n: 2, mean: 1, std: 0, p50: 1, p90: 1, ci95_low: 1, ci95_high: 1 } } },
    { params: { servers: 1, load: 0.9 }, n: 2, metrics: { m: { n: 2, mean: 500, std: 0, p50: 500, p90: 500, ci95_low: 500, ci95_high: 500 } } },
    { params: { servers: 2, load: 0.9 }, n: 2, metrics: { m: { n: 2, mean: 50, std: 0, p50: 50, p90: 50, ci95_low: 50, ci95_high: 50 } } },
    { params: { servers: 4, load: 0.9 }, n: 2, metrics: { other: { n: 2, mean: 7, std: 0, p50: 7, p90: 7, ci95_low: 7, ci95_high: 7 } } },
  ]
  const summary = { combos, sensitivity: [], sensitivity_note: '', ci_note: '' } as BatchSummary

  it('only offers params with a modal slice of 3+ values', () => {
    expect(sweepParamOptions(summary, grid)).toEqual(['servers'])
    expect(sweepParamOptions(undefined, grid)).toEqual([])
  })

  it('builds sorted mean series holding other numeric params at modal value', () => {
    const s = buildSweep(summary, grid, 'servers', 'm')
    expect(s?.others).toEqual({ load: 0.5 })
    expect(s?.series.data).toEqual([
      [1, 100],
      [2, 10],
      [4, 1],
    ])
  })

  it('returns null when the slice has fewer than two points for the metric', () => {
    expect(buildSweep(summary, grid, 'servers', 'other')).toBeNull()
    expect(buildSweep(undefined, grid, 'servers', 'm')).toBeNull()
  })

  it('extracts the 95% CI band only when repeats give real width', () => {
    // fixture above has ci95_low == ci95_high (degenerate) -> no band
    expect(buildSweep(summary, grid, 'servers', 'm')?.band).toBeNull()
    const wide: BatchSummary['combos'] = [
      { params: { servers: 1, load: 0.5 }, n: 5, metrics: { m: { n: 5, mean: 100, std: 8, p50: 100, p90: 104, ci95_low: 93, ci95_high: 107 } } },
      { params: { servers: 2, load: 0.5 }, n: 5, metrics: { m: { n: 5, mean: 10, std: 2, p50: 10, p90: 12, ci95_low: 8.2, ci95_high: 11.8 } } },
      { params: { servers: 4, load: 0.5 }, n: 5, metrics: { m: { n: 5, mean: 1, std: 0.4, p50: 1, p90: 1.5, ci95_low: 0.65, ci95_high: 1.35 } } },
      { params: { servers: 1, load: 0.9 }, n: 5, metrics: { m: { n: 5, mean: 500, std: 10, p50: 500, p90: 510, ci95_low: 491, ci95_high: 509 } } },
      { params: { servers: 2, load: 0.9 }, n: 5, metrics: { m: { n: 5, mean: 50, std: 5, p50: 50, p90: 55, ci95_low: 46, ci95_high: 54 } } },
      { params: { servers: 4, load: 0.9 }, n: 5, metrics: { m: { n: 5, mean: 5, std: 1, p50: 5, p90: 6, ci95_low: 4.1, ci95_high: 5.9 } } },
    ]
    const s2 = buildSweep({ combos: wide, sensitivity: [], sensitivity_note: '', ci_note: '' } as BatchSummary, grid, 'servers', 'm')
    expect(s2?.band?.data).toEqual([
      [1, 93, 107],
      [2, 8.2, 11.8],
      [4, 0.65, 1.35],
    ])
    expect(s2?.band?.color).toContain('rgba(37, 99, 235')
  })

  it('appends CI qualification to jump findings only when decidable', () => {
    const base = { type: 'jump' as const, param: 'servers', from: 1, to: 2, metric: 'm', value_from: 100, value_to: 10, ratio: 10 }
    expect(formatFinding({ ...base, ci_overlap: false })).toContain('置信区间不重叠，跳变显著')
    expect(formatFinding({ ...base, ci_overlap: true })).toContain('可能落在重复间噪声范围内')
    expect(formatFinding(base)).not.toContain('置信区间')
    expect(formatFinding({ ...base, ci_overlap: null, ratio: null, value_from: 0, value_to: 5 })).not.toContain('置信区间')
    expect(formatFinding({ ...base, ci_overlap: false, ratio: null, value_from: 0, value_to: 5 })).toContain('置信区间不重叠，跳变显著')
  })

  it('defaults to the metric named by a jump finding', () => {
    const combos2 = [
      { params: { x: 1 }, n: 1, metrics: { a: { n: 1, mean: 1, std: 0, p50: 1, p90: 1, ci95_low: 1, ci95_high: 1 }, b: { n: 1, mean: 2, std: 0, p50: 2, p90: 2, ci95_low: 2, ci95_high: 2 } } },
      { params: { x: 2 }, n: 1, metrics: { a: { n: 1, mean: 3, std: 0, p50: 3, p90: 3, ci95_low: 3, ci95_high: 3 }, b: { n: 1, mean: 4, std: 0, p50: 4, p90: 4, ci95_low: 4, ci95_high: 4 } } },
      { params: { x: 3 }, n: 1, metrics: { a: { n: 1, mean: 5, std: 0, p50: 5, p90: 5, ci95_low: 5, ci95_high: 5 }, b: { n: 1, mean: 6, std: 0, p50: 6, p90: 6, ci95_low: 6, ci95_high: 6 } } },
    ]
    const sum2 = { combos: combos2, sensitivity: [], sensitivity_note: '', ci_note: '' } as BatchSummary
    const noHit = defaultSweepSelection(sum2, { x: [1, 2, 3] })
    expect(noHit?.metric).toBe('a')
    const hit = defaultSweepSelection(sum2, { x: [1, 2, 3] }, [{ type: 'jump', param: 'x', metric: 'b' }])
    expect(hit?.metric).toBe('b')
  })
})

describe('chartRender', () => {
  it('bounds degrade for empty series and clamp yMin to zero', () => {
    expect(seriesBounds([])).toEqual({ xMin: 0, xMax: 1, yMin: 0, yMax: 1 })
    const b = seriesBounds([{ name: 'a', color: '#000', data: [[2, 4], [6, 10]] }])
    expect(b).toEqual({ xMin: 2, xMax: 6, yMin: 0, yMax: 10 })
  })

  it('niceMax rounds up to 1/2/5 magnitudes', () => {
    expect(niceMax(0)).toBe(1)
    expect(niceMax(1)).toBe(1)
    expect(niceMax(3)).toBe(5)
    expect(niceMax(30)).toBe(50)
    expect(niceMax(250)).toBe(500)
    expect(niceMax(100000)).toBe(100000)
  })

  it('fmtTick keeps integers and compacts thousands', () => {
    expect(fmtTick(3)).toBe('3')
    expect(fmtTick(2.5)).toBe('2.5')
    expect(fmtTick(100000)).toBe('100k')
    expect(fmtTick(150000)).toBe('150k')
  })

  it('ganttRows keeps the most recently active jobs, sorted ascending', () => {
    const segs: [number, number, number][] = [
      [0, 1, 1],
      [2, 3, 2],
      [4, 5, 1],
      [10, 11, 3],
    ]
    expect(ganttRows(segs)).toEqual([1, 2, 3])
    expect(ganttRows(segs, 2)).toEqual([1, 3])
    expect(ganttRows([])).toEqual([])
  })

  it('ganttExtent degrades degenerate ranges', () => {
    expect(ganttExtent([])).toEqual({ tMin: 0, tMax: 1 })
    expect(ganttExtent([[2, 5, 0], [1, 3, 0]] as [number, number, number][])).toEqual({ tMin: 1, tMax: 5 })
    expect(ganttExtent([[2, 2, 1]] as [number, number, number][])).toEqual({ tMin: 2, tMax: 3 })
  })

  it('runsFromBits run-length encodes hit/miss stretches', () => {
    expect(runsFromBits([])).toEqual([])
    expect(runsFromBits([1, 1, 0, 1, 1, 1])).toEqual([
      { hit: true, count: 2 },
      { hit: false, count: 1 },
      { hit: true, count: 3 },
    ])
  })
})

describe('parseArrayText', () => {
  it('parses comma, space and semicolon separated integers', () => {
    expect(parseArrayText('1,2,3', 'integer')).toEqual([1, 2, 3])
    expect(parseArrayText('1 2  3', 'integer')).toEqual([1, 2, 3])
    expect(parseArrayText('1;2,3', 'integer')).toEqual([1, 2, 3])
  })
  it('rejects non-integer or non-numeric tokens for numeric lists', () => {
    expect(parseArrayText('abc', 'integer')).toBeNull()
    expect(parseArrayText('1,x,3', 'integer')).toBeNull()
    expect(parseArrayText('1.5', 'integer')).toBeNull()
    expect(parseArrayText('1.5', 'number')).toEqual([1.5])
  })
  it('treats empty text as cleared', () => {
    expect(parseArrayText('', 'integer')).toBeNull()
    expect(parseArrayText('  ', 'number')).toBeNull()
  })
  it('parses JSON arrays for nested or object items', () => {
    expect(parseArrayText('[[0,1],[1,0]]', 'array')).toEqual([
      [0, 1],
      [1, 0],
    ])
    expect(parseArrayText('[{"duration":5}]', undefined)).toEqual([{ duration: 5 }])
  })
  it('rejects non-array JSON for complex items', () => {
    expect(parseArrayText('{"a":1}', 'array')).toBeNull()
    expect(parseArrayText('not json', undefined)).toBeNull()
  })
})

describe('stepProblem (server-provided step bound, R47)', () => {
  it('blocks values the backend would reject and accepts the bound itself', () => {
    expect(stepProblem(1_000_000, '2000000')).toBe('步数不能超过 1000000')
    expect(stepProblem(1_000_000, '1000000')).toBeNull()
    expect(stepProblem(1_000_000, '1')).toBeNull()
  })
  it('rejects empty, zero, negative and non-integer input', () => {
    expect(stepProblem(1_000_000, '')).toContain('不小于 1')
    expect(stepProblem(1_000_000, '0')).toContain('不小于 1')
    expect(stepProblem(1_000_000, '-3')).toContain('不小于 1')
    expect(stepProblem(1_000_000, '2.5')).toContain('整数')
  })
})

describe('historyHeading (truncation transparency, R48)', () => {
  it('names the total when everything is shown and the cut when it is not', () => {
    expect(historyHeading(0, 0)).toBe('实验历史')
    expect(historyHeading(5, 5)).toBe('实验历史（共 5 条）')
    expect(historyHeading(20, 22)).toBe('实验历史（显示最近 20 条 / 共 22 条，更早的未在界面列出）')
  })
})

describe('toggleCompare (visible compare cap, R49)', () => {
  it('adds below the cap, removes when present, and refuses past the cap', () => {
    expect(toggleCompare([], 1, 4)).toEqual([1])
    expect(toggleCompare([1, 2], 3, 4)).toEqual([1, 2, 3])
    expect(toggleCompare([1, 2, 3], 2, 4)).toEqual([1, 3])
    expect(toggleCompare([1, 2, 3, 4], 5, 4)).toEqual([1, 2, 3, 4])
    // 已选项始终可以取消，即使列表恰好在上限
    expect(toggleCompare([1, 2, 3, 4], 1, 4)).toEqual([2, 3, 4])
  })
})

describe('isSessionGone (session TTL recovery, R50)', () => {
  it('only treats 404s on session paths as a gone session', () => {
    expect(isSessionGone(new ApiError(404, '/api/sessions/abc', 'not_found', 'session not found'))).toBe(true)
    // 别的资源 404（例如删掉的实验）不能清掉当前会话
    expect(isSessionGone(new ApiError(404, '/api/experiments/1', 'not_found', 'experiment 1 not found'))).toBe(false)
    expect(isSessionGone(new ApiError(409, '/api/sessions/abc', 'conflict', 'stopping'))).toBe(false)
    expect(isSessionGone(new Error('network down'))).toBe(false)
    // R51：通用版本按路径段区分资源
    expect(isNotFoundOn(new ApiError(404, '/api/batches/7', 'not_found', 'x'), '/batches/')).toBe(true)
    expect(isNotFoundOn(new ApiError(404, '/api/batches/7', 'not_found', 'x'), '/sessions/')).toBe(false)
    expect(isNotFoundOn(new Error('network down'), '/batches/')).toBe(false)
  })
})

describe('batchesHeading (batch list truncation, R57)', () => {
  it('states the total and the cut when the list is only the latest page', () => {
    expect(batchesHeading(0, 0)).toBe('批量实验')
    expect(batchesHeading(3, 3)).toBe('批量实验（共 3 条）')
    expect(batchesHeading(10, 19)).toBe('批量实验（显示最近 10 条 / 共 19 条，更早的未在界面列出）')
  })
})

describe('historyMoreLabel (history paging, R75)', () => {
  it('shows the remaining count and disappears when everything is loaded', () => {
    expect(historyMoreLabel(20, 25)).toBe('加载更多（还有 5 条）')
    expect(historyMoreLabel(25, 25)).toBeNull()
    expect(historyMoreLabel(0, 0)).toBeNull()
  })
})

