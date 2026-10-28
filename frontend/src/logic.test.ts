import { describe, it, expect } from 'vitest'
import { modelTypeLabel, quickPicks, scenarioSpec, statusLabel } from './App'
import { formatValue } from './SimView'
import { parseValues } from './BatchPanel'
import { resolve } from './ParamForm'
import { summarizeMetrics } from './summary'
import { computeBounds, edgeCells, parseNetwork } from './trafficRender'
import { fmtTick, ganttExtent, ganttRows, niceMax, runsFromBits, seriesBounds } from './chartRender'
import type { JSONSchema } from './schema'
import type { ModelInfo, ScenarioInfo } from './types'

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
    ]
    expect(quickPicks(models).map((p) => p.model.model_id)).toEqual([
      'cellular_automaton',
      'queueing',
      'traffic_network',
    ])
    expect(quickPicks(models)[0].scenario.id).toBe('game-of-life')
  })

  it('skips missing models or scenarios instead of throwing', () => {
    expect(quickPicks([])).toEqual([])
    expect(quickPicks([mkModel('queueing', ['nope'])])).toEqual([])
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
