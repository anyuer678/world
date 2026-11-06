import { useEffect, useRef, useState } from 'react'
import { api, isNotFoundOn } from './api'
import type { ModelInfo, ModelSpec, ScenarioInfo, SessionState } from './types'
import ParamForm from './ParamForm'
import TrafficPanel from './TrafficPanel'
import SimView from './SimView'
import { statusLabel } from './labels'
import BatchPanel from './BatchPanel'
import ComparePanel from './ComparePanel'
import { summarizeMetrics } from './summary'

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
  // R47：单次步进上限从 /api/limits 取（取不到时用与后端一致的保守默认值）
  const [stepMax, setStepMax] = useState(1_000_000)
  // R60：实验名称上限由服务端导出，输入框直接拦住超长名称
  const [nameMax, setNameMax] = useState(200)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [history, setHistory] = useState<{ id: number; name: string; model_id: string; status: string }[]>([])
  // R48：历史只取最近一页，必须把总数一起显示，否则用户会以为看到的就是全部
  const [historyTotal, setHistoryTotal] = useState(0)
  // R75：历史分页——「加载更多」按 offset 追加，直到取满总数
  const [historyLimit, setHistoryLimit] = useState(HISTORY_PAGE_SIZE)
  const sessionRef = useRef<string | null>(null)
  const simSectionRef = useRef<HTMLElement | null>(null)
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
    api
      .getLimits()
      .then((l) => {
        setStepMax(l.session.max_step_batch)
        setNameMax(l.experiment.name_max_length)
      })
      .catch(() => {
        /* 保持保守默认值，不阻塞表单 */
      })
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
        .catch((e) => {
          // R50：以前这里把错误整个吞掉——会话被 TTL 回收后，界面会永远停在「运行中」
          // 且不再更新。只剩 404 需要处理；网络闪断继续轮询即可。
          if (isSessionGone(e) && sessionRef.current === sid) {
            setSession(null)
            setNotice('会话已被服务端回收（空闲超时）或删除；请重新开始模拟。')
          }
        })
    }, 300)
    return () => clearInterval(t)
  }, [session?.status, session?.session_id])

  // 后台标签页的定时器会被浏览器强节流（最长约 1 分钟一次），
  // 标签页重新可见时立即拉取一次真实状态，避免回到页面后看到过期画面
  useEffect(() => {
    const onVisible = () => {
      const sid = sessionRef.current
      if (document.visibilityState === 'visible' && sid) {
        // R51：这里原先也是空 catch——标签页隐藏期间会话被回收时，回到页面只会继续
        // 显示过期画面（此时轮询早已停止，没有第二条路径能发现）。与轮询同一套恢复逻辑。
        api
          .getSession(sid)
          .then((s) => {
            if (sessionRef.current === sid) setSession(s)
          })
          .catch((e) => {
            if (isSessionGone(e) && sessionRef.current === sid) {
              setSession(null)
              setNotice('会话已被服务端回收（空闲超时）或删除；请重新开始模拟。')
            }
          })
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

  async function runScenario(modelId: string, scenario: ScenarioInfo) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const sv = Number(stopValue)
      const current = {
        stop_condition:
          stopType === 'until_empty'
            ? ({ type: 'until_empty' } as const)
            : Number.isFinite(sv) && sv > 0
              ? ({ type: stopType, value: sv } as const)
              : ({ type: 'steps', value: 1000 } as const),
        seed: seed === '' ? null : Number(seed),
      }
      const spec = scenarioSpec(modelId, scenario, current)
      applySpec(spec)
      const s = await api.createSession(spec)
      setSession(s)
      setNotice(`已按场景「${scenario.title}」创建会话，正在连续运行。`)
      simSectionRef.current?.scrollIntoView({ block: 'start' })
      setSession(await api.runSession(s.session_id))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  function refreshHistory() {
    api.listExperiments(historyLimit, 0).then((r) => {
      setHistory(r.experiments)
      setHistoryTotal(r.total)
    })
  }

  async function loadMoreHistory() {
    setBusy(true)
    try {
      const r = await api.listExperiments(HISTORY_PAGE_SIZE, history.length)
      const seen = new Set(history.map((h) => h.id))
      setHistory([...history, ...r.experiments.filter((h) => !seen.has(h.id))])
      setHistoryTotal(r.total)
      setHistoryLimit((n) => n + HISTORY_PAGE_SIZE)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
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
      if (isSessionGone(e)) {
        setSession(null)
        setNotice('会话已被服务端回收（空闲超时）或删除；请重新开始模拟。')
      } else {
        setError(e instanceof Error ? e.message : String(e))
      }
    } finally {
      setBusy(false)
    }
  }

  const st = session?.status ?? null
  const canStep = session !== null && (st === 'idle' || st === 'paused')
  const stepProblemMsg = stepProblem(stepMax, stepN)
  const canRun = session !== null && (st === 'idle' || st === 'paused')
  const canPause = st === 'running'
  const stepCount = session?.snapshot.step ?? 0
  const simTime = session?.snapshot.time ?? 0
  const metrics = session?.snapshot.metrics ?? {}
  const events = session?.events ?? []
  const summary = session ? summarizeMetrics(session.visualizer.kind, metrics) : []

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
      setNotice(`已保存为新实验 #${id}，并按当前表单配置完成一次全新运行（非存档本次会话结果）。`)
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
      // R46：孤儿模型的实验仍可读（R35），但载入时就要说清它跑不了，
      // 而不是等用户点「开始实时模拟」再吃一个英文 422。目录为空（拉取失败）时不误报。
      const stillAvailable = models.length === 0 || models.some((m) => m.model_id === r.experiment.model_id)
      setNotice(
        stillAvailable
          ? `已载入实验 #${id} 的配置（模型 ${r.experiment.model_id} v${r.experiment.model_version}）。`
          : `已载入实验 #${id} 的配置，但其模型 ${r.experiment.model_id} 已不在当前模型目录中——配置可查看，运行会被拒绝。`,
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const model = models.find((m) => m.model_id === selected)

  return (
    <main style={{ fontFamily: 'system-ui, sans-serif', maxWidth: 1100, margin: '0 auto', padding: 24 }}>
      <h1 style={{ borderBottom: '2px solid #2563eb', paddingBottom: 8 }}>WorldLab 模拟工作台</h1>

      {error && (
        <p role="alert" style={{ color: '#dc2626', background: '#fef2f2', padding: '8px 12px', borderRadius: 6 }}>错误：{error}</p>
      )}
      {notice && (
        <p role="status" style={{ color: '#166534', background: '#f0fdf4', padding: '8px 12px', borderRadius: 6 }}>{notice}</p>
      )}

      <section style={card} ref={simSectionRef}>
        <h2>1. 实时模拟视图</h2>
        {session === null ? (
          <>
            <p style={{ color: '#6b7280' }}>
              尚未开始模拟。点下面任一场景立即看结果，或到下方「模型与参数」配置后运行。↓
            </p>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {quickPicks(models).map(({ model, scenario }) => (
                <button
                  key={scenario.id}
                  onClick={() => runScenario(model.model_id, scenario)}
                  disabled={busy}
                  aria-label={`一键运行场景：${scenario.title}`}
                  style={{ ...btn, color: '#2563eb', borderColor: '#bfdbfe' }}
                >
                  ▶ {scenario.title}
                </button>
              ))}
            </div>
          </>
        ) : (
          <>
            <p style={{ fontSize: 13, color: '#374151' }}>
              会话 <code>{session.session_id.slice(0, 8)}…</code> · 模型 {session.display_name} ·{' '}
              {/* role=status：状态由 300ms 轮询异步变化，读屏用户需要被告知「运行中→已暂停」 */}
              <span role="status">
                状态 <strong>{statusLabel(session.status)}</strong>
                {session.stop_reason ? `（${session.stop_reason}）` : ''}
              </span>
            </p>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12, alignItems: 'center' }}>
              <button
                onClick={() => act(() => api.stepSession(session.session_id, Math.max(1, Number(stepN) || 1)))}
                disabled={busy || !canStep || stepProblemMsg !== null}
                style={btn}
                title={stepProblemMsg ?? undefined}
              >
                单步 ×{Math.max(1, Number(stepN) || 1)}
              </button>
              <label style={{ ...rowFlex, margin: 0 }}>
                步数：
                <input
                  value={stepN}
                  onChange={(e) => setStepN(e.target.value)}
                  min={1}
                  max={stepMax}
                  aria-invalid={stepProblemMsg !== null}
                  aria-describedby={stepProblemMsg ? 'step-problem' : undefined}
                  style={{ ...control, width: 70 }}
                />
              </label>
              {stepProblemMsg && (
                <span id="step-problem" role="alert" style={{ color: '#b91c1c', fontSize: 12 }}>
                  {stepProblemMsg}
                </span>
              )}
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
                💾 存配置为新实验并运行
              </button>
            </div>

            {session.error && (
              <p role="alert" style={{ color: '#dc2626', background: '#fef2f2', padding: '6px 10px', borderRadius: 6, fontSize: 13 }}>
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

            {summary.length > 0 && (
              <div
                style={{
                  background: '#eff6ff',
                  border: '1px solid #bfdbfe',
                  borderRadius: 8,
                  padding: '10px 12px',
                  fontSize: 13,
                  color: '#1e3a8a',
                  margin: '12px 0 4px',
                }}
              >
                <strong style={{ display: 'block', marginBottom: 4 }}>结果速读</strong>
                {summary.map((s, i) => (
                  <div key={i}>{s}</div>
                ))}
              </div>
            )}

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

      <section style={card}>
        <h2>2. 模型与参数</h2>
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'flex-start' }}>
          <div style={{ flex: 1, minWidth: 300 }}>
            <label style={rowFlex}>
              模型：
              <select
                value={selected}
                onChange={(e) => applyModel(models.find((m) => m.model_id === e.target.value)!)}
                style={control}
              >
                {models.map((m) => (
                  <option key={m.model_id} value={m.model_id}>
                    {m.display_name}
                  </option>
                ))}
              </select>
            </label>
            {model && (
              <p style={{ color: '#6b7280', fontSize: 12, margin: '2px 0 6px' }}>
                内部标识 {model.model_id} · v{model.version} · {modelTypeLabel(model.model_type)}
              </p>
            )}
            {model?.description && <p style={{ color: '#666', fontSize: 13 }}>{model.description}</p>}
            {model && model.scenarios?.length > 0 && (
              <div style={{ margin: '8px 0 4px' }}>
                <h3 style={{ fontSize: 14, marginBottom: 6 }}>一键场景</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {model.scenarios.map((sc) => (
                    <button
                      key={sc.id}
                      onClick={() => runScenario(model.model_id, sc)}
                      disabled={busy}
                      aria-label={`一键运行场景：${sc.title}`}
                      style={scenarioCard}
                    >
                      <strong style={{ fontSize: 13 }}>{sc.title}</strong>
                      <span style={{ fontSize: 12, color: '#6b7280', fontWeight: 400 }}>{sc.description}</span>
                      <span style={{ fontSize: 12, color: '#2563eb', fontWeight: 600 }}>▶ 一键运行</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
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
              <input value={name} onChange={(e) => setName(e.target.value)} maxLength={nameMax} style={control} />
            </label>
            <button onClick={() => act(() => api.createSession(buildSpec()))} disabled={busy || !selected} style={primaryBtn}>
              开始实时模拟
            </button>
          </div>
          <div style={{ flex: 2, minWidth: 380 }}>
            <h3 style={{ fontSize: 14 }}>
              {selected === 'traffic_network' ? '路网配置（预设 + JSON 编辑 + 预览）' : '参数配置（结构化编辑器，由 params_schema 生成）'}
            </h3>
            {model ? (
              selected === 'traffic_network' ? (
                <TrafficPanel params={params} onChange={setParams} />
              ) : (
                <ParamForm schema={model.params_schema as never} value={params} onChange={setParams} />
              )
            ) : (
              <p style={{ color: '#6b7280' }}>加载中…</p>
            )}
          </div>
        </div>
      </section>

      {session !== null && events.length > 0 && (
        <section style={card}>
          <h2>3. 事件日志（最近 {events.length} 条，来自真实运行）</h2>
          <div
            style={{ maxHeight: 240, overflowY: 'auto', fontFamily: 'monospace', fontSize: 12 }}
            role="region"
            aria-label="事件日志滚动区"
            tabIndex={0}
          >
            {events.map((e) => (
              <div key={e.seq}>
                t={e.time.toFixed(4)} [{e.kind}] {e.message}
              </div>
            ))}
          </div>
        </section>
      )}

      <section style={card}>
        <h2>4. {historyHeading(history.length, historyTotal)}</h2>
        {history.length === 0 ? (
          <p style={{ color: '#6b7280' }}>暂无实验。在上方保存会话配置为实验。</p>
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
                  <td style={td}>{statusLabel(h.status)}</td>
                  <td style={td}>
                    <button onClick={() => loadExperiment(h.id)} style={{ ...btn, padding: '4px 10px', fontSize: 12 }}>
                      载入配置
                    </button>{' '}
                    <a
                      href={api.reportUrl(h.id, 'markdown')}
                      download={`worldlab-report-${h.id}.md`}
                      aria-label={`导出实验 ${h.id} 的 Markdown 报告`}
                      style={{ ...btn, padding: '4px 10px', fontSize: 12, textDecoration: 'none', display: 'inline-block' }}
                    >
                      报告MD
                    </a>{' '}
                    <a
                      href={api.reportUrl(h.id, 'json')}
                      download={`worldlab-report-${h.id}.json`}
                      aria-label={`导出实验 ${h.id} 的 JSON 报告`}
                      style={{ ...btn, padding: '4px 10px', fontSize: 12, textDecoration: 'none', display: 'inline-block' }}
                    >
                      报告JSON
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {history.length > 0 && history.length < historyTotal && (
          <button onClick={loadMoreHistory} disabled={busy} style={{ ...btn, marginTop: 8 }}>
            {historyMoreLabel(history.length, historyTotal)}
          </button>
        )}
      </section>
      <details style={{ ...card, padding: 0 }}>
        <summary style={{ padding: '12px 16px', cursor: 'pointer', fontWeight: 600, fontSize: 15 }}>
          高级：批量实验与结果比较
        </summary>
        <div style={{ padding: '0 16px 12px' }}>
          <h3 style={{ fontSize: 14 }}>批量实验与参数搜索</h3>
          <BatchPanel spec={buildSpec()} />
          <h3 style={{ fontSize: 14, marginTop: 16 }}>结果比较</h3>
          <ComparePanel history={history} historyTotal={historyTotal} />
        </div>
      </details>
    </main>
  )
}

/** 404 + 会话路径才算「会话已不在」（R50）。不能只看 404：
 * 删除一条实验也会 404，但那不该把当前会话清掉。 */
export function isSessionGone(e: unknown): boolean {
  return isNotFoundOn(e, '/sessions/')
}

/** 实验历史的截断口径（R48）：与批量面板的 itemsHeading 同一原则——
 * 只展示一页时必须同时给出总数，否则「最近 20 条」会被误读成「全部 20 条」。 */
/** 每页条数（R75）：与后端 `/api/experiments?limit` 的上限 1000 相容。 */
export const HISTORY_PAGE_SIZE = 20

/** 「加载更多」按钮文案（R75）；已取满返回 null（调用方据此隐藏按钮）。 */
export function historyMoreLabel(shown: number, total: number): string | null {
  if (shown >= total) return null
  return `加载更多（还有 ${total - shown} 条）`
}

export function historyHeading(shown: number, total: number): string {
  if (total <= 0) return '实验历史'
  if (shown >= total) return `实验历史（共 ${total} 条）`
  return `实验历史（显示最近 ${shown} 条 / 共 ${total} 条，更早的未在界面列出）`
}

/** 单步输入的本地校验（R47）：与 /api/limits 的 session.max_step_batch 同源，
 * 让越界在提交前就不可达，而不是发出去吃 422。 */
export function stepProblem(max: number, raw: string): string | null {
  const n = Number(raw)
  if (raw.trim() === '' || !Number.isFinite(n) || !Number.isInteger(n) || n < 1)
    return '步数需为不小于 1 的整数'
  if (n > max) return `步数不能超过 ${max}`
  return null
}

export function modelTypeLabel(t: string): string {
  if (t === 'discrete_event') return '离散事件'
  if (t === 'time_stepped') return '时间步进'
  return t
}

export function scenarioSpec(
  modelId: string,
  scenario: ScenarioInfo,
  current?: { stop_condition: ModelSpec['stop_condition']; seed: number | null },
): ModelSpec {
  const stop = scenario.stop_condition ?? current?.stop_condition ?? { type: 'steps', value: 1000 }
  return {
    schema_version: 1,
    model_id: modelId,
    params: structuredClone(scenario.params),
    stop_condition: structuredClone(stop),
    seed: scenario.seed != null ? scenario.seed : (current?.seed ?? null),
  }
}

const QUICK_PICKS: { modelId: string; scenarioId: string }[] = [
  { modelId: 'schelling', scenarioId: 'mild-preference' },
  { modelId: 'cellular_automaton', scenarioId: 'game-of-life' },
  { modelId: 'queueing', scenarioId: 'rush-hour' },
  { modelId: 'traffic_network', scenarioId: 'no-signal' },
  { modelId: 'sir', scenarioId: 'outbreak' },
  { modelId: 'predator_prey', scenarioId: 'neutral-cycles' },
  { modelId: 'cpu_scheduling', scenarioId: 'rr-quantum-too-small' },
  { modelId: 'cache_sim', scenarioId: 'zipf-hit-ceiling' },
]

export function quickPicks(models: ModelInfo[]): { model: ModelInfo; scenario: ScenarioInfo }[] {
  const out: { model: ModelInfo; scenario: ScenarioInfo }[] = []
  for (const { modelId, scenarioId } of QUICK_PICKS) {
    const model = models.find((m) => m.model_id === modelId)
    const scenario = model?.scenarios.find((s) => s.id === scenarioId)
    if (model && scenario) out.push({ model, scenario })
  }
  return out
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
const scenarioCard: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'flex-start',
  gap: 4,
  padding: '10px 12px',
  background: 'white',
  border: '1px solid #d1d5db',
  borderRadius: 8,
  textAlign: 'left',
  cursor: 'pointer',
}
