import { useState } from 'react'
import type { ExperimentResult, RunDetail } from './types'
import { statusLabel } from './labels'
import { api } from './api'

/** 结果表里要显示的指标列：各次运行的指标并集，按名称排序（R82）。
 * 不能用某一次运行的键集——并行重复里失败的运行通常没有指标。 */
export function metricColumns(runs: { metrics: Record<string, number> | null }[]): string[] {
  return [...new Set(runs.flatMap((r) => Object.keys(r.metrics ?? {})))].sort()
}

/** 汇总口径（R112）：后端 aggregate 只平均 `completed` 且有指标的运行。
 * 标题不能写「全部运行」——混合状态时那会把失败/取消的 run 也算进去（与实现不符）。 */
export function aggregateHeading(runs: { status: string; metrics: Record<string, number> | null }[]): string {
  const countable = runs.filter(
    (r) => r.status === 'completed' && r.metrics && Object.keys(r.metrics).length > 0,
  ).length
  if (countable === runs.length) return `汇总指标（全部 ${runs.length} 次运行）`
  return `汇总指标（仅 ${countable} 次已完成运行，共 ${runs.length} 次）`
}

export default function ResultPanel({ result, onClose }: { result: ExperimentResult; onClose: () => void }) {
  const { experiment, runs, aggregate } = result
  const cols = metricColumns(runs)
  // R85：单次运行详情（GET /api/runs/{id}）此前只有 API，没有界面入口
  const [detail, setDetail] = useState<RunDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState<number | null>(null)
  const [detailError, setDetailError] = useState('')

  async function openRunDetail(runId: number) {
    setDetailLoading(runId)
    setDetailError('')
    try {
      // 运行事件落库上限 100 条；一次取满即可，分页端点留给更大的未来数据量
      setDetail(await api.getRun(runId, 100))
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : String(e))
    } finally {
      setDetailLoading(null)
    }
  }
  return (
    <section aria-label="实验结果详情" style={card}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
        <h2 style={{ margin: '4px 0' }}>实验结果 #{experiment.id}</h2>
        <button onClick={onClose} aria-label="关闭实验结果" style={btn}>
          关闭
        </button>
      </div>
      <p style={{ fontSize: 13, color: '#374151', margin: '4px 0 10px' }}>
        {experiment.name} · 模型 {experiment.model_id} v{experiment.model_version} · 状态{' '}
        {statusLabel(experiment.status)} · 共 {runs.length} 次运行
      </p>
      {experiment.error && (
        <p role="alert" style={{ color: '#b91c1c', background: '#fef2f2', padding: '6px 10px', borderRadius: 6 }}>
          实验错误：{experiment.error}
        </p>
      )}

      {runs.length === 0 ? (
        <p style={{ color: '#6b7280' }}>该实验还没有运行记录。到「载入配置」后点「存配置为新实验并运行」即可产生结果。</p>
      ) : (
        <>
          <h3 style={{ fontSize: 14 }}>{aggregateHeading(runs)}</h3>
          {aggregate && Object.keys(aggregate).length > 0 ? (
            <table style={{ borderCollapse: 'collapse', fontSize: 13, marginBottom: 12 }}>
              <thead>
                <tr>
                  <th style={th}>指标</th>
                  <th style={th}>值</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(aggregate)
                  .sort(([a], [b]) => a.localeCompare(b))
                  .map(([k, v]) => (
                    <tr key={k}>
                      <td style={td}>{k}</td>
                      <td style={td}>{typeof v === 'number' ? v.toFixed(4) : '—'}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          ) : (
            <p style={{ color: '#6b7280', fontSize: 13 }}>暂无可汇总的指标（运行可能未成功完成）。</p>
          )}

          <h3 style={{ fontSize: 14 }}>每次运行</h3>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr>
                  <th style={th}>运行</th>
                  <th style={th}>种子</th>
                  <th style={th}>状态</th>
                  <th style={th}>步数</th>
                  <th style={th}>模拟时间</th>
                  <th style={th}>耗时</th>
                  {cols.map((k) => (
                    <th key={k} style={th}>
                      {k}
                    </th>
                  ))}
                  <th style={th}>详情</th>
                  <th style={th}>错误</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id}>
                    <td style={td}>#{run.id}</td>
                    <td style={td}>{run.seed}</td>
                    <td style={td}>{statusLabel(run.status)}</td>
                    <td style={td}>{run.steps != null ? run.steps : '—'}</td>
                    <td style={td}>{run.sim_time != null ? run.sim_time.toFixed(3) : '—'}</td>
                    <td style={td}>{run.duration_ms != null ? `${(run.duration_ms / 1000).toFixed(2)} s` : '—'}</td>
                    {cols.map((k) => (
                      <td key={k} style={td}>
                        {typeof run.metrics?.[k] === 'number' ? run.metrics[k].toFixed(4) : '—'}
                      </td>
                    ))}
                    <td style={td}>
                      <button
                        onClick={() => openRunDetail(run.id)}
                        disabled={detailLoading !== null}
                        aria-label={`查看运行 ${run.id} 的事件`}
                        style={btn}
                      >
                        {detailLoading === run.id ? '加载中…' : '详情'}
                      </button>
                    </td>
                    <td style={{ ...td, color: run.error ? '#b91c1c' : undefined, maxWidth: 260 }}>{run.error ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {detailError && (
            <p role="alert" style={{ color: '#b91c1c', fontSize: 13 }}>
              运行详情加载失败：{detailError}
            </p>
          )}
          {detail && (
            <div
              aria-label="运行详情"
              style={{ border: '1px solid #d1d5db', borderRadius: 6, padding: '8px 12px', marginTop: 10, background: 'white' }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                <h3 style={{ fontSize: 14, margin: '2px 0' }}>运行 #{detail.id} 详情</h3>
                <button onClick={() => setDetail(null)} aria-label="关闭运行详情" style={btn}>
                  关闭
                </button>
              </div>
              <p style={{ fontSize: 12, color: '#374151', margin: '2px 0 6px' }}>
                {statusLabel(detail.status)} · 种子 {detail.seed} · 步数 {detail.steps ?? '—'} · 模拟时间{' '}
                {detail.sim_time != null ? detail.sim_time.toFixed(3) : '—'} · 耗时{' '}
                {detail.duration_ms != null ? `${(detail.duration_ms / 1000).toFixed(2)} s` : '—'}
              </p>
              <p style={{ fontSize: 11, color: '#6b7280', margin: '0 0 6px', wordBreak: 'break-all' }}>
                结果 SHA-256：{detail.result_sha256 ?? '—'}
              </p>
              {detail.error && (
                <p role="alert" style={{ color: '#b91c1c', fontSize: 12 }}>
                  运行错误：{detail.error}
                </p>
              )}
              <h4 style={{ fontSize: 13, margin: '6px 0 4px' }}>
                事件（最近 {detail.events.length} 条；服务端最多保存 100 条）
              </h4>
              {detail.events.length > 0 ? (
                <div
                  role="region"
                  aria-label="运行事件列表"
                  tabIndex={0}
                  style={{ maxHeight: 200, overflowY: 'auto', fontFamily: 'monospace', fontSize: 12 }}
                >
                  {detail.events.map((ev) => (
                    <div key={ev.seq}>
                      t={ev.time.toFixed(4)} [{ev.kind}] {ev.message}
                    </div>
                  ))}
                </div>
              ) : (
                <p style={{ color: '#6b7280', fontSize: 12 }}>该运行没有保存事件。</p>
              )}
            </div>
          )}
        </>
      )}
    </section>
  )
}

const card: React.CSSProperties = {
  border: '1px solid #e5e7eb',
  borderRadius: 8,
  padding: '12px 16px',
  margin: '16px 0',
  background: '#fafafa',
}
const th: React.CSSProperties = {
  textAlign: 'left',
  borderBottom: '1px solid #d1d5db',
  padding: '4px 8px',
  whiteSpace: 'nowrap',
}
const td: React.CSSProperties = {
  borderBottom: '1px solid #e5e7eb',
  padding: '4px 8px',
  whiteSpace: 'nowrap',
}
const btn: React.CSSProperties = {
  border: '1px solid #d1d5db',
  borderRadius: 6,
  padding: '4px 10px',
  background: 'white',
  cursor: 'pointer',
  fontSize: 12,
}
