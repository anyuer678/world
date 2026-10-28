import { describe, it, expect } from 'vitest'
import { modelTypeLabel, quickPicks, scenarioSpec, statusLabel } from './App'
import { formatValue } from './SimView'
import { parseValues } from './BatchPanel'
import { parseArrayText, resolve } from './ParamForm'
import { summarizeMetrics } from './summary'
import { formatFinding } from './findings'
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
      mkModel('cpu_scheduling', ['rr-quantum-too-small']),
      mkModel('cache_sim', ['zipf-hit-ceiling']),
    ]
    expect(quickPicks(models).map((p) => p.model.model_id)).toEqual([
      'schelling',
      'cellular_automaton',
      'queueing',
      'traffic_network',
      'sir',
      'cpu_scheduling',
      'cache_sim',
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
