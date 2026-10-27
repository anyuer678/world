import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import type { BatchDetail, BatchItem, BatchListItem, ModelSpec } from './types'

const TERMINAL = new Set(['completed', 'failed', 'cancelled'])
const BATCH_ITEM_CAP = 2000

interface GridRow {
  param: string
  values: string
}

export default function BatchPanel({ spec }: { spec: ModelSpec }) {
  const [rows, setRows] = useState<GridRow[]>([{ param: '', values: '' }])
  const [name, setName] = useState('参数网格批量')
  const [repeats, setRepeats] = useState('3')
  const [strategy, setStrategy] = useState('fixed')
  const [retries, setRetries] = useState('0')
  const [wallSec, setWallSec] = useState('60')
  const [batches, setBatches] = useState<BatchListItem[]>([])
  const [batch, setBatch] = useState<BatchDetail | null>(null)
  const [items, setItems] = useState<BatchItem[]>([])
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  const refreshBatches = useCallback(() => {
    api.listBatches().then((r) => setBatches(r.batches)).catch(() => {})
  }, [])

  useEffect(() => {
    refreshBatches()
  }, [refreshBatches])

  // 选中的批量未到终态时轮询；结束后拉取 items（summary 随详情返回）
  useEffect(() => {
    if (batch === null || TERMINAL.has(batch.status)) return
    const id = batch.id
    const t = setInterval(async () => {
      try {
        const b = await api.getBatch(id)
        setBatch(b)
        if (TERMINAL.has(b.status)) {
          setItems((await api.listBatchItems(id, 50)).items)
          refreshBatches()
        }
      } catch {
        /* transient poll errors ignored */
      }
    }, 700)
    return () => clearInterval(t)
  }, [batch, refreshBatches])

  function parseValues(raw: string): unknown[] {
    return raw
      .split(/[,\s]+/)
      .filter(Boolean)
      .map((tok) => (/^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(tok) ? Number(tok) : tok))
  }

  function buildGrid(): Record<string, unknown[]> {
    const grid: Record<string, unknown[]> = {}
    for (const r of rows) {
      const key = r.param.trim()
      if (!key) continue
      grid[key] = parseValues(r.values)
    }
    return grid
  }

  const grid = buildGrid()
  const comboCount = Object.values(grid).reduce((a, v) => a * v.length, 1) || 1
  const repeatN = Math.max(1, Number(repeats) || 1)
  const totalItems = comboCount * repeatN
  const overCap = totalItems > BATCH_ITEM_CAP

  async function submit() {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const b = await api.createBatch({
        name,
        spec,
        grid,
        repeats: repeatN,
        seed_strategy: strategy,
        max_retries: Math.max(0, Number(retries) || 0),
        per_run_wall_seconds: Math.max(1, Number(wallSec) || 60),
      })
      setBatch(b)
      setNotice(`批量 #${b.id} 已创建（${b.total_items} 项），运行中…`)
      refreshBatches()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function openBatch(id: number) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const b = await api.getBatch(id)
      setBatch(b)
      setItems(b.status === 'queued' || b.status === 'running' ? [] : (await api.listBatchItems(id, 50)).items)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function cancel() {
    if (batch === null) return
    setBusy(true)
    setError('')
    try {
      setBatch(await api.cancelBatch(batch.id))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const done = batch
    ? Object.entries(batch.counts).reduce((a, [k, v]) => a + (TERMINAL.has(k) ? v : 0), 0)
    : 0
  const active = batch !== null && !TERMINAL.has(batch.status)

  return (
    <>
      {error && (
        <p style={{ color: '#dc2626', background: '#fef2f2', padding: '6px 10px', borderRadius: 6, fontSize: 13 }}>
          错误：{error}
        </p>
      )}
      {notice && <p style={{ color: '#166534', fontSize: 13 }}>{notice}</p>}
      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <div style={{ flex: 2, minWidth: 320 }}>
          <h3 style={{ fontSize: 14 }}>参数网格（留空网格 = 纯重复试验；值用逗号分隔）</h3>
          {rows.map((r, i) => (
            <div key={i} style={{ display: 'flex', gap: 8, margin: '6px 0' }}>
              <input
                aria-label={`参数名 ${i + 1}`}
                placeholder="参数名（如 servers）"
                value={r.param}
                onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, param: e.target.value } : x)))}
                style={{ ...control, flex: 1 }}
              />
              <input
                aria-label={`参数取值 ${i + 1}`}
                placeholder="取值列表（如 1, 2, 4）"
                value={r.values}
                onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, values: e.target.value } : x)))}
                style={{ ...control, flex: 2 }}
              />
              <button
                aria-label={`删除参数行 ${i + 1}`}
                onClick={() => setRows(rows.filter((_, j) => j !== i))}
                disabled={rows.length === 1}
                style={smallBtn}
              >
                ✕
              </button>
            </div>
          ))}
          <button onClick={() => setRows([...rows, { param: '', values: '' }])} style={{ ...smallBtn, marginTop: 4 }}>
            + 添加参数
          </button>
          <p style={{ fontSize: 13, color: '#374151' }}>
            组合数 {comboCount} × 每组重复 {repeatN} = {totalItems} 项
            {overCap && <strong style={{ color: '#dc2626' }}>（超过上限 {BATCH_ITEM_CAP}，无法提交）</strong>}
          </p>
        </div>
        <div style={{ flex: 1, minWidth: 220 }}>
          <label style={rowFlex}>
            批量名称：
            <input value={name} onChange={(e) => setName(e.target.value)} style={control} />
          </label>
          <label style={rowFlex}>
            每组重复：
            <input value={repeats} onChange={(e) => setRepeats(e.target.value)} style={control} />
          </label>
          <label style={rowFlex}>
            种子策略：
            <select value={strategy} onChange={(e) => setStrategy(e.target.value)} style={control}>
              <option value="fixed">fixed（同种子，配对比较）</option>
              <option value="per_repeat_increment">per_repeat_increment（按重复递增）</option>
              <option value="unique">unique（每项唯一）</option>
            </select>
          </label>
          <label style={rowFlex}>
            失败重试：
            <input value={retries} onChange={(e) => setRetries(e.target.value)} style={control} />
          </label>
          <label style={rowFlex}>
            单项墙钟（秒）：
            <input value={wallSec} onChange={(e) => setWallSec(e.target.value)} style={control} />
          </label>
          <button onClick={submit} disabled={busy || overCap || !name.trim()} style={primaryBtn}>
            启动批量实验
          </button>
          <p style={{ fontSize: 12, color: '#6b7280' }}>
            使用上方「模型与参数」中的当前配置作为基础 spec；网格参数在其之上做笛卡尔积。
          </p>
        </div>
      </div>

      {batches.length > 0 && (
        <table style={table}>
          <thead>
            <tr>
              <th style={th}>#</th>
              <th style={th}>名称</th>
              <th style={th}>模型</th>
              <th style={th}>状态</th>
              <th style={th}>进度</th>
              <th style={th}>操作</th>
            </tr>
          </thead>
          <tbody>
            {batches.map((b) => (
              <tr key={b.id}>
                <td style={td}>{b.id}</td>
                <td style={td}>{b.name}</td>
                <td style={td}>{b.model_id}</td>
                <td style={td}>{b.status}</td>
                <td style={td}>
                  {b.done_items}/{b.total_items}
                </td>
                <td style={td}>
                  <button onClick={() => openBatch(b.id)} disabled={busy} style={{ ...smallBtn, padding: '4px 10px' }}>
                    查看
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {batch !== null && (
        <div style={{ marginTop: 16, borderTop: '1px dashed #d1d5db', paddingTop: 12 }}>
          <p style={{ fontSize: 13, color: '#374151' }}>
            批量 #{batch.id}「{batch.name}」 · 模型 {batch.model_id} v{batch.model_version} · 状态{' '}
            <strong>{batch.status}</strong> · 种子策略 {batch.seed_strategy}（基种子 {batch.seed_base ?? '—'}）
          </p>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', margin: '8px 0' }}>
            <div style={{ background: '#e5e7eb', borderRadius: 4, height: 10, flex: 1, overflow: 'hidden' }}>
              <div
                style={{
                  background: '#2563eb',
                  height: '100%',
                  width: `${batch.total_items ? Math.min(100, (done / batch.total_items) * 100) : 0}%`,
                  transition: 'width 0.3s',
                }}
              />
            </div>
            <span style={{ fontSize: 13 }}>
              {done}/{batch.total_items}
            </span>
            <button onClick={cancel} disabled={busy || !active} style={{ ...smallBtn, ...(active ? {} : { opacity: 0.5 }) }}>
              取消批量
            </button>
          </div>
          {Object.keys(batch.counts).length > 0 && (
            <p style={{ fontSize: 12, color: '#6b7280' }}>
              {Object.entries(batch.counts)
                .map(([k, v]) => `${k}: ${v}`)
                .join(' · ')}
            </p>
          )}
          {batch.error && <p style={{ color: '#dc2626', fontSize: 13 }}>批量错误：{batch.error}</p>}

          {batch.summary && batch.summary.combos.length > 0 && (
            <>
              <h4 style={{ fontSize: 14, marginBottom: 4 }}>统计汇总（按参数组合）</h4>
              <div style={{ maxHeight: 300, overflowY: 'auto' }}>
                <table style={table}>
                  <thead>
                    <tr>
                      <th style={th}>参数组合</th>
                      <th style={th}>指标</th>
                      <th style={th}>n</th>
                      <th style={th}>均值</th>
                      <th style={th}>标准差</th>
                      <th style={th}>p50</th>
                      <th style={th}>p90</th>
                      <th style={th}>95% CI</th>
                    </tr>
                  </thead>
                  <tbody>
                    {batch.summary.combos.map((c, i) =>
                      Object.entries(c.metrics).map(([metric, s], j) => (
                        <tr key={`${i}-${metric}`}>
                          {j === 0 && (
                            <td style={{ ...td, fontFamily: 'monospace', fontSize: 12 }} rowSpan={Object.keys(c.metrics).length}>
                              {JSON.stringify(c.params)}
                            </td>
                          )}
                          <td style={td}>{metric}</td>
                          <td style={td}>{s.n}</td>
                          <td style={td}>{s.mean.toFixed(4)}</td>
                          <td style={td}>{s.std.toFixed(4)}</td>
                          <td style={td}>{s.p50.toFixed(4)}</td>
                          <td style={td}>{s.p90.toFixed(4)}</td>
                          <td style={td}>
                            [{s.ci95_low.toFixed(3)}, {s.ci95_high.toFixed(3)}]
                          </td>
                        </tr>
                      )),
                    )}
                  </tbody>
                </table>
              </div>
              <p style={{ fontSize: 12, color: '#6b7280' }}>{batch.summary.ci_note}</p>
              {batch.summary.sensitivity.length > 0 && (
                <>
                  <h4 style={{ fontSize: 14, marginBottom: 4 }}>参数敏感性（皮尔逊相关）</h4>
                  <ul style={{ fontSize: 13, margin: '4px 0', paddingLeft: 20 }}>
                    {batch.summary.sensitivity.map((s) => (
                      <li key={`${s.param}-${s.metric}`}>
                        {s.param} ↔ {s.metric}：r = {s.pearson_r}（{s.n_combos} 个组合）
                      </li>
                    ))}
                  </ul>
                </>
              )}
              <p style={{ fontSize: 12, color: '#92400e', background: '#fffbeb', padding: '6px 10px', borderRadius: 6 }}>
                {batch.summary.sensitivity_note}
              </p>
            </>
          )}

          {items.length > 0 && (
            <>
              <h4 style={{ fontSize: 14, marginBottom: 4 }}>单项结果（前 {items.length} 项）</h4>
              <div style={{ maxHeight: 260, overflowY: 'auto' }}>
                <table style={table}>
                  <thead>
                    <tr>
                      <th style={th}>#</th>
                      <th style={th}>组合</th>
                      <th style={th}>seed</th>
                      <th style={th}>状态</th>
                      <th style={th}>尝试</th>
                      <th style={th}>steps</th>
                      <th style={th}>指标</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((it) => (
                      <tr key={it.id}>
                        <td style={td}>{it.item_index}</td>
                        <td style={{ ...td, fontFamily: 'monospace', fontSize: 12 }}>{JSON.stringify(it.params)}</td>
                        <td style={td}>{it.seed}</td>
                        <td style={td}>{it.status}</td>
                        <td style={td}>{it.attempts}</td>
                        <td style={td}>{it.steps ?? '—'}</td>
                        <td style={{ ...td, fontFamily: 'monospace', fontSize: 12 }}>
                          {it.metrics ? JSON.stringify(it.metrics) : it.error || '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}
    </>
  )
}

const rowFlex: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 8, margin: '6px 0' }
const control: React.CSSProperties = { flex: 1, padding: 6, border: '1px solid #d1d5db', borderRadius: 6 }
const smallBtn: React.CSSProperties = {
  border: '1px solid #d1d5db',
  borderRadius: 6,
  padding: '6px 10px',
  background: 'white',
  cursor: 'pointer',
  fontSize: 13,
}
const primaryBtn: React.CSSProperties = {
  border: '1px solid #2563eb',
  borderRadius: 6,
  padding: '8px 14px',
  background: '#2563eb',
  color: 'white',
  cursor: 'pointer',
  fontSize: 14,
  marginTop: 6,
}
const table: React.CSSProperties = { borderCollapse: 'collapse', width: '100%', fontSize: 13 }
const th: React.CSSProperties = { textAlign: 'left', borderBottom: '2px solid #e5e7eb', padding: '6px 8px' }
const td: React.CSSProperties = { borderBottom: '1px solid #f0f0f0', padding: '6px 8px' }
