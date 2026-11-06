import { statusLabel } from './labels'
import { useEffect, useState } from 'react'
import { api } from './api'
import type { ExperimentResult } from './types'

interface HistoryEntry {
  id: number
  name: string
  model_id: string
  status: string
}

export const MAX_COMPARE = 4

/** 勾选/取消比较项。达到上限时**保持原样**由调用方负责提示——
 * 这里不做静默截断之外的任何改变，纯函数便于单测（R49）。 */
export function toggleCompare(ids: number[], id: number, max: number): number[] {
  if (ids.includes(id)) return ids.filter((x) => x !== id)
  if (ids.length >= max) return ids
  return [...ids, id]
}

/** 比较结果的失效键（R110）：选择变化或所选实验状态变化时，上次抓取的表格就不再对应当前状态。
 * 用字符串键而不是数组依赖，避免历史轮询每次返回新数组就把结果清空。 */
export function compareSignature(selected: number[], history: HistoryEntry[]): string {
  return selected.map((id) => `${id}:${history.find((h) => h.id === id)?.status ?? 'gone'}`).join(',')
}

export default function ComparePanel({
  history,
  historyTotal = history.length,
}: {
  history: HistoryEntry[]
  historyTotal?: number
}) {
  const [selected, setSelected] = useState<number[]>([])
  const [results, setResults] = useState<ExperimentResult[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setSelected((s) => s.filter((id) => history.some((h) => h.id === id)))
  }, [history])

  // 选择或所选实验状态变化后，旧的比较结果不再代表当前状态；清空让用户重新比较（R110）
  const signature = compareSignature(selected, history)
  useEffect(() => {
    setResults([])
  }, [signature])

  function toggle(id: number) {
    setSelected((s) => toggleCompare(s, id, MAX_COMPARE))
  }

  async function compare() {
    setBusy(true)
    setError('')
    try {
      setResults(await Promise.all(selected.map((id) => api.getResult(id))))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const rows = results.flatMap((r) =>
    r.runs.map((run) => ({
      expId: r.experiment.id,
      expName: r.experiment.name,
      model: `${r.experiment.model_id} v${r.experiment.model_version}`,
      seed: run.seed,
      status: run.status,
      metrics: run.metrics ?? {},
    })),
  )
  const metricKeys = [...new Set(rows.flatMap((r) => Object.keys(r.metrics)))].sort()
  const models = [...new Set(rows.map((r) => r.model))]
  const crossModel = models.length > 1

  return (
    <>
      {history.length === 0 ? (
        <p style={{ color: '#6b7280' }}>暂无实验可比较。</p>
      ) : (
        <>
          {history.length < historyTotal && (
            <p style={{ color: '#92400e', fontSize: 12, margin: '0 0 6px' }}>
              可选范围：最近 {history.length} 条（共 {historyTotal} 条；更早的实验未在界面列出）
            </p>
          )}
          <p
            id="compare-cap"
            style={{ color: selected.length >= MAX_COMPARE ? '#92400e' : '#6b7280', fontSize: 12, margin: '0 0 6px' }}
          >
            最多同时比较 {MAX_COMPARE} 个（已选 {selected.length} / {MAX_COMPARE}）
            {selected.length >= MAX_COMPARE ? '——已达上限，取消一个后可再选' : ''}
          </p>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
            {history.map((h) => {
              const checked = selected.includes(h.id)
              return (
                <label key={h.id} style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 4 }}>
                  <input
                    type="checkbox"
                    checked={checked}
                    // 到顶时禁用未选项：与其让点击无声失败，不如让「不能再选」直接可见
                    disabled={!checked && selected.length >= MAX_COMPARE}
                    onChange={() => toggle(h.id)}
                    aria-label={`选择实验 ${h.id}`}
                    aria-describedby="compare-cap"
                  />
                  #{h.id} {h.name}（{h.model_id}）
                </label>
              )
            })}
          </div>
          <button onClick={compare} disabled={busy || selected.length < 1} style={btn}>
            比较所选实验（≤{MAX_COMPARE} 个）
          </button>
        </>
      )}

      {crossModel && (
        <p style={{ fontSize: 13, color: '#92400e', background: '#fffbeb', padding: '6px 10px', borderRadius: 6 }}>
          注意：所选实验来自不同模型或不同模型版本，其指标默认不可直接比较，仅供参考。
        </p>
      )}

      {error && <p style={{ color: '#dc2626', fontSize: 13 }}>错误：{error}</p>}

      {rows.length > 0 && (
        <div style={{ maxHeight: 300, overflowY: 'auto', marginTop: 8 }}>
          <table style={table}>
            <thead>
              <tr>
                <th style={th}>实验</th>
                <th style={th}>模型</th>
                <th style={th}>seed</th>
                <th style={th}>状态</th>
                {metricKeys.map((k) => (
                  <th key={k} style={th}>
                    {k}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td style={td}>
                    #{r.expId} {r.expName}
                  </td>
                  <td style={td}>{r.model}</td>
                  <td style={td}>{r.seed}</td>
                  <td style={td}>{statusLabel(r.status)}</td>
                  {metricKeys.map((k) => (
                    <td key={k} style={td}>
                      {typeof r.metrics[k] === 'number' ? r.metrics[k].toFixed(4) : '—'}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}

const btn: React.CSSProperties = {
  border: '1px solid #d1d5db',
  borderRadius: 6,
  padding: '8px 14px',
  background: 'white',
  cursor: 'pointer',
  fontSize: 14,
  margin: '8px 0',
}
const table: React.CSSProperties = { borderCollapse: 'collapse', width: '100%', fontSize: 13 }
const th: React.CSSProperties = { textAlign: 'left', borderBottom: '2px solid #e5e7eb', padding: '6px 8px' }
const td: React.CSSProperties = { borderBottom: '1px solid #f0f0f0', padding: '6px 8px' }
