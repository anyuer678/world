import type { SessionState } from './types'

export default function SimView({ session }: { session: SessionState }) {
  const { visualizer, snapshot } = session
  if (visualizer.kind === 'queue') return <QueueView state={snapshot.state} />
  return <StateTable state={snapshot.state} />
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

function formatValue(v: unknown): string {
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(4)
  if (Array.isArray(v)) return `[${v.length} 项]`
  if (v !== null && typeof v === 'object') return JSON.stringify(v).slice(0, 80)
  return String(v)
}
