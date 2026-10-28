import { describe, it, expect } from 'vitest'
import { statusLabel } from './App'
import { formatValue } from './SimView'
import { parseValues } from './BatchPanel'
import { resolve } from './ParamForm'
import { computeBounds, edgeCells, parseNetwork } from './trafficRender'
import type { JSONSchema } from './schema'

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
