import { useEffect, useRef } from 'react'
import type { SessionState } from './types'
import { drawNetwork, parseNetwork } from './trafficRender'

export default function SimView({ session }: { session: SessionState }) {
  const { visualizer, snapshot } = session
  if (visualizer.kind === 'queue') return <QueueView state={snapshot.state} />
  if (visualizer.kind === 'cpu_schedule') return <CpuScheduleView state={snapshot.state} />
  if (visualizer.kind === 'cache') return <CacheView state={snapshot.state} />
  if (visualizer.kind === 'ca') return <CaView state={snapshot.state} />
  if (visualizer.kind === 'traffic') return <TrafficView state={snapshot.state} />
  return <StateTable state={snapshot.state} />
}

function TrafficView({ state }: { state: Record<string, unknown> }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const net = parseNetwork(state)
  const vehicles = (state.vehicles as [number, number, number][] | undefined) ?? []
  const edgeLoad = (state.edge_load as number[] | undefined) ?? []
  const signals = (state.signals as { node: string; green_group: number }[] | undefined) ?? []
  const history = (state.history as number[] | undefined) ?? []

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !net) return
    canvas.width = 640
    canvas.height = 420
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    drawNetwork(ctx, net, {
      width: 640,
      height: 420,
      padding: 36,
      vehicles: vehicles.map(([edge, cell, v]) => ({ edge, cell, v })),
      edgeLoad,
      signalNodes: signals.map((s) => ({ id: s.node, green: s.green_group === 0 })),
    })
  })

  if (!net) return <p style={{ color: '#888' }}>等待交通快照…</p>

  const hMax = Math.max(...history, 1)
  const points = history
    .map((p, i) => `${(i / Math.max(history.length - 1, 1)) * 300},${60 - (p / hMax) * 56}`)
    .join(' ')

  return (
    <div>
      <canvas
        ref={canvasRef}
        style={{ maxWidth: '100%', border: '1px solid #d1d5db', borderRadius: 4 }}
        role="img"
        aria-label={`交通路网第 ${Number(state.tick ?? 0)} tick，在途车辆 ${Number(state.active ?? 0)} 辆`}
      />
      <svg width="100%" height={80} viewBox="0 0 320 76" role="img" aria-label="在途车辆数历史曲线">
        <text x={0} y={12} fontSize={11} fill="#6b7280">
          在途车辆数（最近 {history.length} tick，峰值 {hMax}）
        </text>
        {history.length > 1 && <polyline points={points} fill="none" stroke="#2563eb" strokeWidth={1.5} />}
      </svg>
      <p style={{ fontSize: 13, color: '#374151', margin: '4px 0' }}>
        第 {Number(state.tick ?? 0)} tick · 在途 {Number(state.active ?? 0)} · 已发车 {Number(state.spawned ?? 0)} · 已完成{' '}
        {Number(state.completed ?? 0)} · 平均行程 {Number(state.avg_travel_time ?? 0).toFixed(1)} tick ·
        红点=停止车辆 · 灰/黄/红路=占用率低/中/高
      </p>
    </div>
  )
}

function CpuScheduleView({ state }: { state: Record<string, unknown> }) {
  const ready = (state.ready as { seq: number; service: number; remaining: number; priority: number }[] | undefined) ?? []
  const running = state.running as { seq: number; remaining: number } | null | undefined
  const readyCount = Number(state.ready_count ?? ready.length)
  const shown = ready.length
  const util = Number(state.cpu_utilization ?? 0)

  return (
    <div>
      <svg width="100%" height={210} viewBox="0 0 640 210" role="img" aria-label="CPU 调度实时状态图">
        <text x={16} y={26} fontSize={13} fill="#374151">
          就绪作业 →
        </text>

        <text x={140} y={22} fontSize={12} fill="#6b7280">
          就绪队列（{readyCount}
          {readyCount > shown ? `，显示前 ${shown}` : ''}）
        </text>
        {Array.from({ length: shown }, (_, i) => {
          const j = ready[i]
          return (
            <g key={j.seq}>
              <rect x={140 + (i % 14) * 34} y={30 + Math.floor(i / 14) * 30} width={30} height={24} fill="#93c5fd" stroke="#3b82f6" rx={2}>
                <title>{`job #${j.seq}：剩余 ${j.remaining} / 服务 ${j.service}，优先级 ${j.priority}`}</title>
              </rect>
              <text x={155 + (i % 14) * 34} y={46 + Math.floor(i / 14) * 30} fontSize={10} textAnchor="middle" fill="#1e3a8a">
                #{j.seq}
              </text>
            </g>
          )
        })}
        {readyCount > shown && (
          <text x={140 + 14 * 34} y={46} fontSize={11} fill="#6b7280">
            +{readyCount - shown} 更多
          </text>
        )}
        {shown === 0 && (
          <text x={140} y={46} fontSize={12} fill="#9ca3af">
            （空）
          </text>
        )}

        <text x={140} y={118} fontSize={12} fill="#6b7280">
          CPU（{running ? '忙' : '空闲'}）
        </text>
        <rect x={140} y={126} width={90} height={48} fill={running ? '#2563eb' : '#f3f4f6'} stroke="#9ca3af" rx={4} />
        {running ? (
          <text x={185} y={154} fontSize={12} textAnchor="middle" fill="white">
            #{running.seq} 余 {running.remaining.toFixed(2)}
          </text>
        ) : (
          <text x={185} y={154} fontSize={12} textAnchor="middle" fill="#9ca3af">
            idle
          </text>
        )}
        {state.quantum != null && (
          <text x={244} y={154} fontSize={12} fill="#6b7280">
            时间片 {String(state.quantum)}
          </text>
        )}
      </svg>
      <p style={{ fontSize: 13, color: '#374151', margin: '4px 0' }}>
        策略 {String(state.strategy ?? '-')} · 已到达 {Number(state.arrived ?? 0)} · 已完成 {Number(state.completed ?? 0)} · 待到达{' '}
        {Number(state.pending_count ?? 0)} · CPU 利用率 {(util * 100).toFixed(1)}%
      </p>
    </div>
  )
}

function CacheView({ state }: { state: Record<string, unknown> }) {
  const contents = (state.contents as number[] | undefined) ?? []
  const capacity = Number(state.capacity ?? 0)
  const slots = capacity > 0 && capacity <= 64 ? capacity : Math.max(contents.length, 1)
  const lastKey = state.last_key as number | null | undefined
  const lastHit = state.last_hit as boolean | null | undefined
  const hitRate = Number(state.hit_rate ?? 0)

  return (
    <div>
      <svg width="100%" height={Math.max(120, 66 + Math.ceil(slots / 8) * 40)} viewBox={`0 0 640 ${Math.max(120, 66 + Math.ceil(slots / 8) * 40)}`} role="img" aria-label="缓存实时状态图">
        <text x={16} y={22} fontSize={13} fill="#374151">
          缓存槽位（{String(state.policy ?? '-')}）
        </text>
        {Array.from({ length: slots }, (_, i) => {
          const key = i < contents.length ? contents[i] : null
          const isLast = key !== null && lastKey != null && key === lastKey
          const fill = key === null ? '#f9fafb' : isLast ? (lastHit ? '#22c55e' : '#f59e0b') : '#93c5fd'
          return (
            <g key={i}>
              <rect x={16 + (i % 8) * 76} y={32 + Math.floor(i / 8) * 40} width={68} height={32} fill={fill} stroke="#9ca3af" rx={3} />
              <text x={50 + (i % 8) * 76} y={52 + Math.floor(i / 8) * 40} fontSize={12} textAnchor="middle" fill={key === null ? '#d1d5db' : '#1e3a8a'}>
                {key === null ? '空' : `key ${key}`}
              </text>
            </g>
          )
        })}
        {capacity > 64 && (
          <text x={16} y={40 + Math.ceil(slots / 8) * 40} fontSize={11} fill="#6b7280">
            仅显示最近访问的前 64 个键（容量 {capacity}）
          </text>
        )}
      </svg>
      <p style={{ fontSize: 13, color: '#374151', margin: '4px 0' }}>
        访问 {Number(state.accesses ?? 0)} 次 · 命中 {Number(state.hits ?? 0)} · 缺失 {Number(state.misses ?? 0)} · 命中率{' '}
        {(hitRate * 100).toFixed(1)}% · 占用 {Number(state.size ?? 0)}/{capacity}
        {state.evicted != null ? ` · 上次驱逐 key ${String(state.evicted)}` : ''}
      </p>
    </div>
  )
}

function CaView({ state }: { state: Record<string, unknown> }) {
  const rows = (state.rows as string[] | undefined) ?? []
  const width = Number(state.width ?? 0)
  const height = Number(state.height ?? 0)
  const history = (state.history as number[] | undefined) ?? []
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || rows.length === 0 || width === 0) return
    const cell = Math.max(1, Math.floor(600 / width))
    canvas.width = width * cell
    canvas.height = height * cell
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.fillStyle = '#f3f4f6'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.fillStyle = '#111827'
    rows.forEach((row, i) => {
      for (let j = 0; j < row.length; j++) {
        if (row[j] === '1') ctx.fillRect(j * cell, i * cell, cell, cell)
      }
    })
  })

  if (rows.length === 0) return <p style={{ color: '#888' }}>尚未初始化（点击「创建会话」后开始模拟）。</p>

  const hMax = Math.max(...history, 1)
  const points = history
    .map((p, i) => `${(i / Math.max(history.length - 1, 1)) * 300},${60 - (p / hMax) * 56}`)
    .join(' ')

  return (
    <div>
      <canvas
        ref={canvasRef}
        style={{ maxWidth: '100%', imageRendering: 'pixelated', border: '1px solid #d1d5db' }}
        role="img"
        aria-label={`元胞自动机第 ${Number(state.generation ?? 0)} 代网格，活细胞 ${Number(state.population ?? 0)} 个`}
      />
      <svg width="100%" height={80} viewBox="0 0 320 76" role="img" aria-label="种群历史曲线">
        <text x={0} y={12} fontSize={11} fill="#6b7280">
          种群历史（最近 {history.length} 代，峰值 {hMax}）
        </text>
        {history.length > 1 && <polyline points={points} fill="none" stroke="#2563eb" strokeWidth={1.5} />}
      </svg>
      <p style={{ fontSize: 13, color: '#374151', margin: '4px 0' }}>
        规则 {String(state.rule ?? '-')} · 第 {Number(state.generation ?? 0)} 代 · 活细胞 {Number(state.population ?? 0)} · 累计出生{' '}
        {Number(state.births_total ?? 0)} · 累计死亡 {Number(state.deaths_total ?? 0)} · 边界
        {state.toroidal ? '环形' : '固定'}
      </p>
    </div>
  )
}

function QueueView({ state }: { state: Record<string, unknown> }) {
  const servers = Math.min(Number(state.servers ?? 0), 16)
  const busy = Math.min(Number(state.busy_servers ?? 0), servers)
  const qlen = Number(state.queue_length ?? 0)
  const shown = Math.min(qlen, 40)

  return (
    <div>
      <svg width="100%" height={170} viewBox="0 0 640 170" role="img" aria-label="排队系统实时状态图">
        <text x={16} y={26} fontSize={13} fill="#374151">
          到达 →
        </text>
        <line x1={70} y1={22} x2={120} y2={22} stroke="#2563eb" strokeWidth={2} markerEnd="url(#arrow)" />
        <defs>
          <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" fill="#2563eb" />
          </marker>
        </defs>

        <text x={140} y={26} fontSize={12} fill="#6b7280">
          等待队列（{qlen}
          {qlen > shown ? `，显示前 ${shown}` : ''}）
        </text>
        {Array.from({ length: shown }, (_, i) => (
          <rect
            key={i}
            x={140 + (i % 20) * 24}
            y={34 + Math.floor(i / 20) * 16}
            width={18}
            height={12}
            fill="#93c5fd"
            stroke="#3b82f6"
            rx={2}
          />
        ))}

        <text x={140} y={92} fontSize={12} fill="#6b7280">
          服务台（{busy}/{String(state.servers ?? servers)} 忙）
        </text>
        {Array.from({ length: servers }, (_, i) => (
          <g key={i}>
            <rect
              x={140 + (i % 8) * 60}
              y={100 + Math.floor(i / 8) * 46}
              width={48}
              height={36}
              fill={i < busy ? '#2563eb' : '#f3f4f6'}
              stroke="#9ca3af"
              rx={4}
            />
            {i < busy && (
              <text x={164 + (i % 8) * 60} y={122 + Math.floor(i / 8) * 46} fontSize={11} fill="white" textAnchor="middle">
                ●
              </text>
            )}
          </g>
        ))}
        {Number(state.servers ?? 0) > 16 && (
          <text x={140 + 8 * 60} y={122} fontSize={12} fill="#6b7280">
            +{Number(state.servers ?? 0) - 16} 更多
          </text>
        )}
      </svg>
      <p style={{ fontSize: 13, color: '#374151', margin: '4px 0' }}>
        在系统 {Number(state.in_system ?? 0)} · 已到达 {Number(state.arrived ?? 0)} · 已服务{' '}
        {Number(state.served ?? 0)} · 丢弃 {Number(state.dropped ?? 0)}
        {state.capacity != null ? ` · 容量上限 ${String(state.capacity)}` : ' · 容量无限'}
      </p>
    </div>
  )
}

function StateTable({ state }: { state: Record<string, unknown> }) {
  const entries = Object.entries(state)
  if (entries.length === 0) return <p style={{ color: '#888' }}>尚未初始化（点击「创建会话」后开始模拟）。</p>
  return (
    <table style={{ borderCollapse: 'collapse', fontSize: 13 }}>
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k}>
            <td style={{ padding: '3px 12px 3px 0', color: '#6b7280' }}>{k}</td>
            <td style={{ padding: '3px 0', fontFamily: 'monospace' }}>{formatValue(v)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function formatValue(v: unknown): string {
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(4)
  if (Array.isArray(v)) return `[${v.length} 项]`
  if (v !== null && typeof v === 'object') return JSON.stringify(v).slice(0, 80)
  return String(v)
}
