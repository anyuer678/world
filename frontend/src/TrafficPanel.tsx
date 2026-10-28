import { useEffect, useMemo, useRef, useState } from 'react'
import { drawNetwork, parseNetwork, type Network } from './trafficRender'

interface SignalLike {
  node: string
  cycle: number
  offset?: number
  group_a: string[]
  group_b: string[]
}

const PRESETS: { key: string; label: string; network: { nodes: unknown[]; edges: unknown[]; signals: SignalLike[] } }[] = [
  {
    key: 'crossroad',
    label: '十字路口（带信号）',
    network: {
      nodes: [
        { id: 'N', x: 0, y: -30 },
        { id: 'E', x: 30, y: 0 },
        { id: 'S', x: 0, y: 30 },
        { id: 'W', x: -30, y: 0 },
        { id: 'C', x: 0, y: 0 },
      ],
      edges: [
        { src: 'N', dst: 'C' },
        { src: 'C', dst: 'S' },
        { src: 'S', dst: 'C' },
        { src: 'C', dst: 'N' },
        { src: 'E', dst: 'C' },
        { src: 'C', dst: 'W' },
        { src: 'W', dst: 'C' },
        { src: 'C', dst: 'E' },
      ],
      signals: [{ node: 'C', cycle: 8, offset: 0, group_a: ['N', 'S'], group_b: ['E', 'W'] }],
    },
  },
  {
    key: 'ring',
    label: '单向环线',
    network: {
      nodes: Array.from({ length: 6 }, (_, i) => ({
        id: `n${i}`,
        x: Math.round(30 * Math.cos((2 * Math.PI * i) / 6) * 100) / 100,
        y: Math.round(30 * Math.sin((2 * Math.PI * i) / 6) * 100) / 100,
      })),
      edges: Array.from({ length: 6 }, (_, i) => ({ src: `n${i}`, dst: `n${(i + 1) % 6}` })),
      signals: [],
    },
  },
  {
    key: 'corridor',
    label: '双向走廊',
    network: {
      nodes: [
        { id: 'A', x: -45, y: 0 },
        { id: 'B', x: -15, y: 0 },
        { id: 'C', x: 15, y: 0 },
        { id: 'D', x: 45, y: 0 },
      ],
      edges: [
        { src: 'A', dst: 'B' },
        { src: 'B', dst: 'A' },
        { src: 'B', dst: 'C' },
        { src: 'C', dst: 'B' },
        { src: 'C', dst: 'D' },
        { src: 'D', dst: 'C' },
      ],
      signals: [{ node: 'C', cycle: 10, offset: 0, group_a: ['B'], group_b: ['D'] }],
    },
  },
  {
    key: 'grid',
    label: '3×3 棋盘路网',
    network: {
      nodes: Array.from({ length: 9 }, (_, i) => ({
        id: `g${i}`,
        x: (i % 3) * 30 - 30,
        y: Math.floor(i / 3) * 30 - 30,
      })),
      edges: (() => {
        const es: { src: string; dst: string }[] = []
        for (let i = 0; i < 9; i++) {
          if (i % 3 < 2) es.push({ src: `g${i}`, dst: `g${i + 1}` }, { src: `g${i + 1}`, dst: `g${i}` })
          if (Math.floor(i / 3) < 2) es.push({ src: `g${i}`, dst: `g${i + 3}` }, { src: `g${i + 3}`, dst: `g${i}` })
        }
        return es
      })(),
      signals: [],
    },
  },
]

function defaultNetworkText(): string {
  return JSON.stringify({ nodes: PRESETS[0].network.nodes, edges: PRESETS[0].network.edges, signals: PRESETS[0].network.signals }, null, 2)
}

export default function TrafficPanel({
  params,
  onChange,
}: {
  params: Record<string, unknown>
  onChange: (v: Record<string, unknown>) => void
}) {
  const [netText, setNetText] = useState<string>(() => {
    const cur = { nodes: params.nodes, edges: params.edges, signals: params.signals }
    if (Array.isArray(cur.nodes) && Array.isArray(cur.edges)) return JSON.stringify(cur, null, 2)
    return defaultNetworkText()
  })
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  // keep the textarea in sync when params are replaced from outside
  // (loading an experiment config) rather than edited here
  const paramsNetKey = useMemo(
    () => JSON.stringify({ nodes: params.nodes, edges: params.edges, signals: params.signals }),
    [params.nodes, params.edges, params.signals],
  )
  const [lastApplied, setLastApplied] = useState<string>(() =>
    Array.isArray(params.nodes) && Array.isArray(params.edges) ? paramsNetKey : '',
  )
  useEffect(() => {
    if (paramsNetKey !== lastApplied && Array.isArray(params.nodes) && Array.isArray(params.edges)) {
      setNetText(JSON.stringify(JSON.parse(paramsNetKey), null, 2))
      setLastApplied(paramsNetKey)
    }
  }, [paramsNetKey, lastApplied, params.nodes, params.edges])

  const parsed = useMemo<{ net: Network | null; signals: SignalLike[]; error: string }>(() => {
    try {
      const obj = JSON.parse(netText) as Record<string, unknown>
      const net = parseNetwork(obj)
      if (!net) return { net: null, signals: [], error: '需要 {nodes: [...], edges: [...], signals: [...]} 结构' }
      const signals = Array.isArray(obj.signals) ? (obj.signals as SignalLike[]) : []
      return { net, signals, error: '' }
    } catch (e) {
      return { net: null, signals: [], error: `JSON 解析失败：${e instanceof Error ? e.message : String(e)}` }
    }
  }, [netText])

  const applyNetwork = (network: Record<string, unknown>) => {
    setNetText(JSON.stringify(network, null, 2))
    setLastApplied(JSON.stringify(network))
    onChange({ ...params, ...network })
  }

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !parsed.net) return
    canvas.width = 340
    canvas.height = 260
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    drawNetwork(ctx, parsed.net, { width: 340, height: 260, padding: 28 })
  }, [parsed])

  const num = (k: string, fallback: number) => {
    const v = params[k]
    return typeof v === 'number' ? v : fallback
  }

  const setScalar = (k: string, v: unknown) => onChange({ ...params, [k]: v })

  const commitNetwork = () => {
    if (!parsed.error && parsed.net) {
      setLastApplied(JSON.stringify({ nodes: parsed.net.nodes, edges: parsed.net.edges, signals: parsed.signals }))
      onChange({ ...params, nodes: parsed.net.nodes, edges: parsed.net.edges, signals: parsed.signals })
    }
  }

  const spawnNodesText = Array.isArray(params.spawn_nodes) ? (params.spawn_nodes as string[]).join(',') : ''
  const signalInfo = parsed.signals
    .map((s) => `${s.node}(周期${s.cycle})`)
    .join('、')

  return (
    <div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
        {PRESETS.map((p) => (
          <button key={p.key} type="button" onClick={() => applyNetwork({ ...p.network })} style={presetBtn}>
            {p.label}
          </button>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <div style={{ flex: 1, minWidth: 280 }}>
          <label style={{ fontSize: 13, display: 'block', color: '#374151' }}>
            路网定义（nodes/edges/signals，JSON）
            <textarea
              value={netText}
              onChange={(e) => setNetText(e.target.value)}
              onBlur={commitNetwork}
              rows={14}
              spellCheck={false}
              style={{ ...control, fontFamily: 'monospace', fontSize: 12, display: 'block', marginTop: 4, width: '100%' }}
              aria-label="路网 JSON 编辑器"
            />
          </label>
          {parsed.error ? (
            <p style={{ color: '#dc2626', fontSize: 12 }} role="alert">
              {parsed.error}
            </p>
          ) : (
            <p style={{ color: '#6b7280', fontSize: 12 }}>
              {parsed.net?.nodes.length ?? 0} 节点 · {parsed.net?.edges.length ?? 0} 边{signalInfo ? ` · 信号：${signalInfo}` : ''}
            </p>
          )}
        </div>
        <div style={{ flex: '0 0 auto' }}>
          <canvas
            ref={canvasRef}
            style={{ border: '1px solid #d1d5db', borderRadius: 6, maxWidth: '100%' }}
            role="img"
            aria-label="路网预览"
          />
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '4px 16px', marginTop: 8 }}>
        <NumField label="最高车速 v_max（格/tick）" value={num('v_max', 2)} min={1} max={10}
          onChange={(v) => setScalar('v_max', v)} />
        <NumField label="随机慢化概率" value={num('slow_prob', 0.15)} min={0} max={1} step={0.05}
          onChange={(v) => setScalar('slow_prob', v)} />
        <NumField label="发车概率（每源节点/tick）" value={num('spawn_rate', 0.4)} min={0} max={1} step={0.05}
          onChange={(v) => setScalar('spawn_rate', v)} />
        <NumField label="车辆上限" value={num('max_vehicles', 300)} min={1} max={100000}
          onChange={(v) => setScalar('max_vehicles', v)} />
        <NumField label="发车截止 tick（留空=一直发车）" value={params.spawn_until == null ? '' : num('spawn_until', 0)}
          min={0} onChange={(v) => setScalar('spawn_until', v)} />
        <label style={row}>
          <span style={labelStyle}>发车源节点（逗号分隔，空=全部）</span>
          <input
            type="text"
            value={spawnNodesText}
            onChange={(e) =>
              setScalar(
                'spawn_nodes',
                e.target.value
                  .split(',')
                  .map((s) => s.trim())
                  .filter(Boolean),
              )
            }
            style={control}
          />
        </label>
      </div>
      <p style={{ color: '#92400e', background: '#fffbeb', fontSize: 12, padding: '6px 10px', borderRadius: 6, marginTop: 8 }}>
        信号灯规则：每个信号节点在 group_a（前半周期放行）与 group_b（后半周期放行）之间交替，两组必须恰好覆盖该节点的全部驶入来源。
      </p>
    </div>
  )
}

function NumField({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string
  value: number | ''
  min?: number
  max?: number
  step?: number
  onChange: (v: number | null) => void
}) {
  return (
    <label style={row}>
      <span style={labelStyle}>{label}</span>
      <input
        type="number"
        value={value === '' ? '' : String(value)}
        min={min}
        max={max}
        step={step ?? 1}
        onChange={(e) => {
          const raw = e.target.value
          if (raw === '') {
            onChange(null)
            return
          }
          const n = Number(raw)
          onChange(Number.isNaN(n) ? null : n)
        }}
        style={control}
      />
    </label>
  )
}

const row: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 8, margin: '6px 0' }
const labelStyle: React.CSSProperties = { fontSize: 13, color: '#374151', flex: 1 }
const control: React.CSSProperties = { flex: 1, padding: 6, border: '1px solid #d1d5db', borderRadius: 6 }
const presetBtn: React.CSSProperties = {
  border: '1px solid #d1d5db',
  borderRadius: 6,
  padding: '5px 10px',
  background: 'white',
  cursor: 'pointer',
  fontSize: 12,
}
