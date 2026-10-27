import { useEffect, useState } from 'react'
import { api } from './api'
import type { ExperimentResult } from './types'

interface HistoryEntry {
  id: number
  name: string
  model_id: string
  status: string
}

const MAX_COMPARE = 4

export default function ComparePanel({ history }: { history: HistoryEntry[] }) {
  const [selected, setSelected] = useState<number[]>([])
  const [results, setResults] = useState<ExperimentResult[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setSelected((s) => s.filter((id) => history.some((h) => h.id === id)))
  }, [history])

  function toggle(id: number) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : s.length < MAX_COMPARE ? [...s, id] : s))
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
        <p style={{ color: '#888' }}>暂无实验可比较。</p>
      ) : (
        <>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
            {history.map((h) => (
              <label key={h.id} style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 4 }}>
                <input
                  type="checkbox"
                  checked={selected.includes(h.id)}
                  onChange={() => toggle(h.id)}
                  aria-label={`选择实验 ${h.id}`}
                />
                #{h.id} {h.name}（{h.model_id}）
              </label>
            ))}
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
                  <td style={td}>{r.status}</td>
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
