import type { ExperimentResult } from './types'
import { statusLabel } from './labels'

/** 结果表里要显示的指标列：各次运行的指标并集，按名称排序（R82）。
 * 不能用某一次运行的键集——并行重复里失败的运行通常没有指标。 */
export function metricColumns(runs: { metrics: Record<string, number> | null }[]): string[] {
  return [...new Set(runs.flatMap((r) => Object.keys(r.metrics ?? {})))].sort()
}

export default function ResultPanel({ result, onClose }: { result: ExperimentResult; onClose: () => void }) {
  const { experiment, runs, aggregate } = result
  const cols = metricColumns(runs)
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
          <h3 style={{ fontSize: 14 }}>汇总指标（全部运行）</h3>
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
                    <td style={{ ...td, color: run.error ? '#b91c1c' : undefined, maxWidth: 260 }}>{run.error ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
