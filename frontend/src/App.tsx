import { useEffect, useRef, useState } from 'react'
import { api } from './api'
import type { ModelInfo, ModelSpec, SessionState } from './types'
import ParamForm from './ParamForm'
import SimView from './SimView'
import BatchPanel from './BatchPanel'
import ComparePanel from './ComparePanel'

type StopType = 'steps' | 'sim_time' | 'until_empty'

export default function App() {
  const [models, setModels] = useState<ModelInfo[]>([])
  const [selected, setSelected] = useState('')
  const [params, setParams] = useState<Record<string, unknown>>({})
  const [seed, setSeed] = useState<string>('42')
  const [stopType, setStopType] = useState<StopType>('steps')
  const [stopValue, setStopValue] = useState<string>('10000')
  const [name, setName] = useState('我的实验')
  const [stepN, setStepN] = useState('1')
  const [session, setSession] = useState<SessionState | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [history, setHistory] = useState<{ id: number; name: string; model_id: string; status: string }[]>([])
  const sessionRef = useRef<string | null>(null)
  sessionRef.current = session?.session_id ?? null

  useEffect(() => {
    api
      .listModels()
      .then(({ models }) => {
        setModels(models)
        if (models.length > 0) applyModel(models[0])
      })
      .catch((e) => setError(String(e)))
    refreshHistory()
  }, [])

  // 会话运行中时轮询真实状态；状态离开 running 后停止
  useEffect(() => {
    if (session?.status !== 'running') return
    const sid = session.session_id
    const t = setInterval(() => {
      api
        .getSession(sid)
        .then((s) => {
          if (sessionRef.current === sid) setSession(s)
        })
        .catch(() => {})
    }, 300)
    return () => clearInterval(t)
  }, [session?.status, session?.session_id])

  // 后台标签页的定时器会被浏览器强节流（最长约 1 分钟一次），
  // 标签页重新可见时立即拉取一次真实状态，避免回到页面后看到过期画面
  useEffect(() => {
    const onVisible = () => {
      const sid = sessionRef.current
      if (document.visibilityState === 'visible' && sid) {
        api.getSession(sid).then(setSession).catch(() => {})
      }
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [])

  function applyModel(m: ModelInfo) {
    setSelected(m.model_id)
    setParams(structuredClone(m.example_spec.params))
    setSeed(m.example_spec.seed != null ? String(m.example_spec.seed) : '')
    setStopType(m.example_spec.stop_condition.type)
    setStopValue(m.example_spec.stop_condition.value != null ? String(m.example_spec.stop_condition.value) : '')
  }

  function applySpec(spec: ModelSpec) {
    setSelected(spec.model_id)
    setParams(structuredClone(spec.params))
    setSeed(spec.seed != null ? String(spec.seed) : '')
    setStopType(spec.stop_condition.type)
    setStopValue(spec.stop_condition.value != null ? String(spec.stop_condition.value) : '')
  }

  function refreshHistory() {
    api.listExperiments().then((r) => setHistory(r.experiments))
  }

  function buildSpec(): ModelSpec {
    return {
      schema_version: 1,
      model_id: selected,
      params,
      stop_condition: stopType === 'until_empty' ? { type: 'until_empty' } : { type: stopType, value: Number(stopValue) },
      seed: seed === '' ? null : Number(seed),
    }
  }

  async function act(fn: () => Promise<SessionState>) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      setSession(await fn())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const st = session?.status ?? null
  const canStep = session !== null && (st === 'idle' || st === 'paused')
  const canRun = session !== null && (st === 'idle' || st === 'paused')
  const canPause = st === 'running'
  const stepCount = session?.snapshot.step ?? 0
  const simTime = session?.snapshot.time ?? 0
  const metrics = session?.snapshot.metrics ?? {}
  const events = session?.events ?? []

  const stop = session?.spec.stop_condition
  const progress =
    stop?.type === 'steps' && stop.value
      ? stepCount / stop.value
      : stop?.type === 'sim_time' && stop.value
        ? simTime / stop.value
        : null

  async function saveAndRunExperiment() {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const { id } = await api.createExperiment(name, buildSpec())
      await api.runExperiment(id, true)
      setNotice(`实验 #${id} 已保存并完成运行，可在下方历史中查看。`)
      refreshHistory()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function loadExperiment(id: number) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const r = await api.getResult(id)
      applySpec(r.experiment.spec)
      if (r.experiment.name) setName(r.experiment.name)
      setNotice(`已载入实验 #${id} 的配置（模型 ${r.experiment.model_id} v${r.experiment.model_version}）。`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const model = models.find((m) => m.model_id === selected)

  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', maxWidth: 1100, margin: '0 auto', padding: 24 }}>
      <h1 style={{ borderBottom: '2px solid #2563eb', paddingBottom: 8 }}>WorldLab 模拟工作台</h1>

      {error && (
        <p style={{ color: '#dc2626', background: '#fef2f2', padding: '8px 12px', borderRadius: 6 }}>错误：{error}</p>
      )}
      {notice && <p style={{ color: '#166534', background: '#f0fdf4', padding: '8px 12px', borderRadius: 6 }}>{notice}</p>}

      <section style={card}>
        <h2>1. 模型与参数</h2>
        <label style={rowFlex}>
          模型：
          <select
            value={selected}
            onChange={(e) => applyModel(models.find((m) => m.model_id === e.target.value)!)}
            style={control}
          >
            {models.map((m) => (
              <option key={m.model_id} value={m.model_id}>
                {m.display_name}（{m.model_id} v{m.version} · {m.model_type}）
              </option>
            ))}
          </select>
        </label>
        {model?.description && <p style={{ color: '#666', fontSize: 13 }}>{model.description}</p>}
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-start' }}>
          <div style={{ flex: 2, minWidth: 320 }}>
            <h3 style={{ fontSize: 14 }}>参数配置（结构化编辑器，由 params_schema 生成）</h3>
            {model ? (
              <ParamForm schema={model.params_schema as never} value={params} onChange={setParams} />
            ) : (
              <p style={{ color: '#888' }}>加载中…</p>
            )}
          </div>
          <div style={{ flex: 1, minWidth: 220 }}>
            <h3 style={{ fontSize: 14 }}>运行控制</h3>
            <label style={rowFlex}>
              随机种子：
              <input value={seed} onChange={(e) => setSeed(e.target.value)} placeholder="留空 = 随机" style={control} />
            </label>
            <label style={rowFlex}>
              停止条件：
              <select value={stopType} onChange={(e) => setStopType(e.target.value as StopType)} style={control}>
                <option value="steps">按步数</option>
                <option value="sim_time">按模拟时间</option>
                <option value="until_empty">直到事件队列为空</option>
              </select>
            </label>
            {stopType !== 'until_empty' && (
              <label style={rowFlex}>
                停止值：
                <input value={stopValue} onChange={(e) => setStopValue(e.target.value)} style={control} />
              </label>
            )}
            <label style={rowFlex}>
              实验名称：
              <input value={name} onChange={(e) => setName(e.target.value)} style={control} />
            </label>
            <button onClick={() => act(() => api.createSession(buildSpec()))} disabled={busy || !selected} style={primaryBtn}>
              创建会话
            </button>
          </div>
        </div>
      </section>

      <section style={card}>
        <h2>2. 实时模拟视图</h2>
        {session === null ? (
          <p style={{ color: '#888' }}>尚未创建会话。配置参数后点击「创建会话」。</p>
        ) : (
          <>
            <p style={{ fontSize: 13, color: '#374151' }}>
              会话 <code>{session.session_id.slice(0, 8)}…</code> · 模型 {session.display_name} · 状态{' '}
              <strong>{statusLabel(session.status)}</strong>
              {session.stop_reason ? `（${session.stop_reason}）` : ''}
            </p>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12, alignItems: 'center' }}>
              <button
                onClick={() => act(() => api.stepSession(session.session_id, Math.max(1, Number(stepN) || 1)))}
                disabled={busy || !canStep}
                style={btn}
              >
                单步 ×{Math.max(1, Number(stepN) || 1)}
              </button>
              <label style={{ ...rowFlex, margin: 0 }}>
                步数：
                <input value={stepN} onChange={(e) => setStepN(e.target.value)} style={{ ...control, width: 70 }} />
              </label>
              <button onClick={() => act(() => api.runSession(session.session_id))} disabled={busy || !canRun} style={primaryBtn}>
                ▶ 连续运行
              </button>
              <button onClick={() => act(() => api.pauseSession(session.session_id))} disabled={busy || !canPause} style={btn}>
                ⏸ 暂停
              </button>
              <button onClick={() => act(() => api.resumeSession(session.session_id))} disabled={busy || st !== 'paused'} style={btn}>
                ⏵ 恢复
              </button>
              <button onClick={() => act(() => api.resetSession(session.session_id))} disabled={busy} style={btn}>
                ↺ 重置
              </button>
              <button onClick={saveAndRunExperiment} disabled={busy || !selected} style={btn}>
                💾 保存为实验并运行
              </button>
            </div>

            {session.error && (
              <p style={{ color: '#dc2626', background: '#fef2f2', padding: '6px 10px', borderRadius: 6, fontSize: 13 }}>
                模拟错误：{session.error}
              </p>
            )}

            <div style={{ margin: '10px 0 4px', fontSize: 13, color: '#374151' }}>
              时间轴：step {stepCount}
              {stop?.type === 'steps' && stop.value ? ` / ${stop.value}` : ''} · sim_time {simTime.toFixed(4)}
            </div>
            <div style={{ background: '#e5e7eb', borderRadius: 4, height: 10, overflow: 'hidden' }}>
              <div
                style={{
                  background: '#2563eb',
                  height: '100%',
                  width: progress != null ? `${Math.min(100, progress * 100)}%` : '0%',
                  transition: 'width 0.2s',
                }}
              />
            </div>

            <h3 style={{ fontSize: 14, marginTop: 14 }}>模拟状态（来自真实快照）</h3>
            <SimView session={session} />

            <h3 style={{ fontSize: 14 }}>指标面板</h3>
            <table style={table}>
              <tbody>
                {Object.entries(metrics).map(([k, v]) => (
                  <tr key={k}>
                    <td style={td}>{k}</td>
                    <td style={td}>{typeof v === 'number' ? v.toFixed(4) : String(v)}</td>
                  </tr>
                ))}
                {Object.keys(metrics).length === 0 && (
                  <tr>
                    <td style={td} colSpan={2}>
                      暂无指标
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </>
        )}
      </section>

      {session !== null && events.length > 0 && (
        <section style={card}>
          <h2>3. 事件日志（最近 {events.length} 条，来自真实运行）</h2>
          <div style={{ maxHeight: 240, overflowY: 'auto', fontFamily: 'monospace', fontSize: 12 }}>
            {events.map((e) => (
              <div key={e.seq}>
                t={e.time.toFixed(4)} [{e.kind}] {e.message}
              </div>
            ))}
          </div>
        </section>
      )}

      <section style={card}>
        <h2>4. 实验历史</h2>
        {history.length === 0 ? (
          <p style={{ color: '#888' }}>暂无实验。在上方保存会话配置为实验。</p>
        ) : (
          <table style={table}>
            <thead>
              <tr>
                <th style={th}>#</th>
                <th style={th}>名称</th>
                <th style={th}>模型</th>
                <th style={th}>状态</th>
                <th style={th}>操作</th>
              </tr>
            </thead>
            <tbody>
              {history.map((h) => (
                <tr key={h.id}>
                  <td style={td}>{h.id}</td>
                  <td style={td}>{h.name}</td>
                  <td style={td}>{h.model_id}</td>
                  <td style={td}>{h.status}</td>
                  <td style={td}>
                    <button onClick={() => loadExperiment(h.id)} style={{ ...btn, padding: '4px 10px', fontSize: 12 }}>
                      载入配置
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <section style={card}>
        <h2>5. 批量实验与参数搜索</h2>
        <BatchPanel spec={buildSpec()} />
      </section>

      <section style={card}>
        <h2>6. 结果比较</h2>
        <ComparePanel history={history} />
      </section>
    </div>
  )
}

function statusLabel(s: string): string {
  const map: Record<string, string> = {
    idle: '就绪',
    running: '运行中',
    paused: '已暂停',
    completed: '已完成',
    cancelled: '已取消',
    error: '出错',
    step_limit: '达步数上限',
    wall_timeout: '超时',
  }
  return map[s] ?? s
}

const card: React.CSSProperties = {
  border: '1px solid #e5e7eb',
  borderRadius: 8,
  padding: '12px 16px',
  margin: '16px 0',
  background: '#fafafa',
}
const rowFlex: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 8, margin: '6px 0' }
const control: React.CSSProperties = { flex: 1, padding: 6, border: '1px solid #d1d5db', borderRadius: 6 }
const btn: React.CSSProperties = {
  border: '1px solid #d1d5db',
  borderRadius: 6,
  padding: '8px 14px',
  background: 'white',
  cursor: 'pointer',
  fontSize: 14,
}
const primaryBtn: React.CSSProperties = {
  ...btn,
  background: '#2563eb',
  color: 'white',
  borderColor: '#2563eb',
}
const table: React.CSSProperties = { borderCollapse: 'collapse', width: '100%', fontSize: 14 }
const th: React.CSSProperties = { textAlign: 'left', borderBottom: '2px solid #e5e7eb', padding: '6px 8px' }
const td: React.CSSProperties = { borderBottom: '1px solid #f0f0f0', padding: '6px 8px' }
