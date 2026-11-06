import { modelVersionLabel, moreLabel, statusLabel } from './labels'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, isNotFoundOn } from './api'
import type { BatchDetail, BatchItem, BatchListItem, ModelInfo, ModelSpec } from './types'
import { formatFinding, type FindingsResponse } from './findings'
import { buildSweep, defaultSweepSelection, sweepMetricOptions, sweepParamOptions, type SweepSelection } from './sweepChart'
import { drawLineChart } from './chartRender'
import { useCanvas } from './SimView'

const TERMINAL = new Set(['completed', 'failed', 'cancelled'])

export interface BatchLimits {
  maxItems: number
  nameMaxLength: number
  repeatsMin: number
  repeatsMax: number
  retriesMin: number
  retriesMax: number
}

/** Used until /api/limits answers; the server stays the source of truth. */
export const FALLBACK_LIMITS: BatchLimits = {
  maxItems: 2000,
  nameMaxLength: 200,
  repeatsMin: 1,
  repeatsMax: 100,
  retriesMin: 0,
  retriesMax: 10,
}

export function batchSubmitProblem(
  limits: BatchLimits,
  opts: { name: string; totalItems: number; repeats: number; retries: number },
): string | null {
  if (!opts.name.trim()) return '批量名称不能为空'
  if (opts.name.length > limits.nameMaxLength) return `批量名称最长 ${limits.nameMaxLength} 字符（当前 ${opts.name.length}）`
  if (opts.repeats < limits.repeatsMin || opts.repeats > limits.repeatsMax)
    return `每组重复需在 ${limits.repeatsMin}–${limits.repeatsMax} 之间（当前 ${opts.repeats}）`
  if (opts.retries < limits.retriesMin || opts.retries > limits.retriesMax)
    return `失败重试需在 ${limits.retriesMin}–${limits.retriesMax} 之间（当前 ${opts.retries}）`
  if (opts.totalItems > limits.maxItems)
    return `总项数 ${opts.totalItems} 超过上限 ${limits.maxItems}：请缩小网格或减少重复`
  return null
}

/**
 * 单项结果表头的诚实口径：接口一次最多取一页，必须把「共多少项」一起显示，
 * 否则 1200 项的批次只出现 50 行会被读成全部数据（完整明细在 CSV 导出里）。
 */
/** 批量列表的截断口径（R57）：只展示最近 10 条时必须给出总数，
 * 否则「10 条」会被当成「全部 10 条」（与 R48 的历史口径一致）。 */
/** 批量列表每页条数（R78，与实验历史的 20 条相互独立）。 */
export const BATCH_PAGE_SIZE = 10
// R92：批量列表可筛选的状态（与后端 BatchStatus Literal 同集合）
export const BATCH_STATUSES = ['queued', 'running', 'completed', 'failed', 'cancelled'] as const
// R86：批单项一次取 50 条；超过时用「加载更多」按 offset 续读（与列表分页同一交互）
export const ITEMS_PAGE_SIZE = 50
// R88：批单项可按状态服务端筛选（与实验历史的筛选同一原则：分页列表不能在客户端过滤）
export const ITEM_STATUSES = [
  'pending',
  'running',
  'completed',
  'failed',
  'cancelled',
  'step_limit',
  'wall_timeout',
] as const

export function batchesHeading(shown: number, total: number): string {
  if (total <= 0) return '批量实验'
  if (shown >= total) return `批量实验（共 ${total} 条）`
  return `批量实验（显示最近 ${shown} 条 / 共 ${total} 条，更早的未在界面列出）`
}

export function itemsHeading(shown: number, total: number): string {
  if (total <= 0 || shown >= total) return `单项结果（全部 ${shown} 项）`
  return `单项结果（显示前 ${shown} / 共 ${total} 项，可继续加载或导出 CSV）`
}

/** 行内取消按钮的可用状态（R93）：与后端 cancel 的 queued/running 语义一致。 */
export function canCancelBatch(status: string): boolean {
  return status === 'queued' || status === 'running'
}

/** 失败项重试入口（R97）：只有 failed 且确有失败项时才显示。 */
export function canRetryFailed(status: string, failed: number): boolean {
  return status === 'failed' && failed > 0
}

export function parseValues(raw: string): unknown[] {
  return raw
    .split(/[,\s]+/)
    .filter(Boolean)
    .map((tok) => (/^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(tok) ? Number(tok) : tok))
}

export interface GridRow {
  param: string
  values: string
}

/** 把批量记录的 grid 还原成表单行（R99）：数字/布尔用 String，其他值 JSON 化。 */
export function gridRowsFromBatch(grid: Record<string, unknown[]>): GridRow[] {
  const rows = Object.entries(grid).map(([param, values]) => ({
    param,
    values: values
      .map((v) => (typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v)))
      .join(', '),
  }))
  return rows.length ? rows : [{ param: '', values: '' }]
}

export default function BatchPanel({
  spec,
  models = [],
  onUseTemplate,
}: {
  spec: ModelSpec
  models?: ModelInfo[]
  onUseTemplate?: (spec: ModelSpec) => void
}) {
  const [rows, setRows] = useState<GridRow[]>([{ param: '', values: '' }])
  const [name, setName] = useState('参数网格批量')
  const [repeats, setRepeats] = useState('3')
  const [strategy, setStrategy] = useState('fixed')
  const [retries, setRetries] = useState('0')
  const [wallSec, setWallSec] = useState('60')
  const [batches, setBatches] = useState<BatchListItem[]>([])
  // R57：列表固定取最近 10 条，必须同时显示总数（与 R48 的实验历史同一口径）
  const [batchesTotal, setBatchesTotal] = useState(0)
  // R78：「加载更多」按 offset 追加（与实验历史 R75 的交互一致）
  const [batchesLimit, setBatchesLimit] = useState(BATCH_PAGE_SIZE)
  // R92：批量列表也支持服务端模型/状态筛选（与实验历史同一原则）
  const [filterModel, setFilterModel] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const batchesSeq = useRef(0)
  const [batch, setBatch] = useState<BatchDetail | null>(null)
  const [items, setItems] = useState<BatchItem[]>([])
  const [itemsTotal, setItemsTotal] = useState(0)
  const [itemStatus, setItemStatus] = useState('')
  // R94：批单项详情（SHA/耗时/模拟时间等字段此前只在 CSV 里）
  const [itemDetail, setItemDetail] = useState<BatchItem | null>(null)
  const [findings, setFindings] = useState<FindingsResponse | null>(null)
  const [sweepSel, setSweepSel] = useState<{ param: string; metric: string } | null>(null)
  const [limits, setLimits] = useState<BatchLimits>(FALLBACK_LIMITS)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  const refreshBatches = useCallback(() => {
    // R51：列表拉取失败此前完全静默——服务端不可达时界面只显示「暂无批量」，
    // 用户会把失败当成「没有数据」。这里至少把原因显示出来。
    const seq = ++batchesSeq.current
    api
      .listBatches(batchesLimit, 0, filterModel || undefined, filterStatus || undefined)
      .then((r) => {
        if (seq !== batchesSeq.current) return
        setBatches(r.batches)
        setBatchesTotal(r.total)
      })
      .catch((e) => {
        if (seq === batchesSeq.current) setError(e instanceof Error ? e.message : String(e))
      })
  }, [batchesLimit, filterModel, filterStatus])

  useEffect(() => {
    refreshBatches()
  }, [refreshBatches])

  // R93：有 queued/running 批量时自动刷新列表——进度与终态不必靠用户打开详情才更新
  const anyActiveBatch = batches.some((b) => canCancelBatch(b.status))
  useEffect(() => {
    if (!anyActiveBatch) return
    const t = setInterval(refreshBatches, 800)
    return () => clearInterval(t)
  }, [anyActiveBatch, refreshBatches])

  async function loadMoreBatches() {
    setBusy(true)
    const seq = ++batchesSeq.current
    try {
      const r = await api.listBatches(
        BATCH_PAGE_SIZE,
        batches.length,
        filterModel || undefined,
        filterStatus || undefined,
      )
      if (seq !== batchesSeq.current) return
      const seen = new Set(batches.map((b) => b.id))
      setBatches([...batches, ...r.batches.filter((b) => !seen.has(b.id))])
      setBatchesTotal(r.total)
      setBatchesLimit((n) => n + BATCH_PAGE_SIZE)
    } catch (e) {
      if (seq === batchesSeq.current) setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  function changeBatchModel(value: string) {
    setBatchesLimit(BATCH_PAGE_SIZE)
    setFilterModel(value)
  }

  function changeBatchStatus(value: string) {
    setBatchesLimit(BATCH_PAGE_SIZE)
    setFilterStatus(value)
  }

  function clearBatchFilters() {
    setBatchesLimit(BATCH_PAGE_SIZE)
    setFilterModel('')
    setFilterStatus('')
  }

  async function loadMoreItems() {
    if (!batch) return
    setBusy(true)
    try {
      const page = await api.listBatchItems(
        batch.id,
        ITEMS_PAGE_SIZE,
        items.length,
        itemStatus || undefined,
      )
      const seen = new Set(items.map((it) => it.id))
      setItems([...items, ...page.items.filter((it) => !seen.has(it.id))])
      setItemsTotal(page.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function changeItemStatus(status: string) {
    if (!batch) return
    setItemStatus(status)
    setItemDetail(null)
    setBusy(true)
    setError('')
    try {
      const page = await api.listBatchItems(batch.id, ITEMS_PAGE_SIZE, 0, status || undefined)
      setItems(page.items)
      setItemsTotal(page.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  // 提交上限取自服务端 /api/limits（R29）：取不到时用 FALLBACK_LIMITS，不阻塞表单
  useEffect(() => {
    api
      .getLimits()
      .then((r) =>
        setLimits({
          maxItems: r.batch.max_items,
          nameMaxLength: r.batch.name_max_length,
          repeatsMin: r.batch.repeats_min,
          repeatsMax: r.batch.repeats_max,
          retriesMin: r.batch.max_retries_min,
          retriesMax: r.batch.max_retries_max,
        }),
      )
      .catch(() => {})
  }, [])

  // 选中的批量未到终态时轮询；结束后拉取 items 与自动发现（summary 随详情返回）
  useEffect(() => {
    if (batch === null || TERMINAL.has(batch.status)) return
    const id = batch.id
    const t = setInterval(async () => {
      try {
        const b = await api.getBatch(id)
        setBatch(b)
        if (TERMINAL.has(b.status)) {
          const page = await api.listBatchItems(id, ITEMS_PAGE_SIZE, 0, itemStatus || undefined)
          setItems(page.items)
          setItemsTotal(page.total)
          api.getBatchFindings(id).then(setFindings).catch(() => {})
          refreshBatches()
        }
      } catch (e) {
        // 404 不是抖动：批量已不存在（外部删除/库被重置），继续轮询只会永远停在旧数据
        if (isNotFoundOn(e, '/batches/')) {
          setError('批量已不存在（可能被外部删除或数据库被重置）')
          setBatch(null)
        }
        /* 其余视为瞬时错误，继续轮询 */
      }
    }, 700)
    return () => clearInterval(t)
  }, [batch, refreshBatches, itemStatus])

  // 打开的批量到达终态且用户未手动选过切片时，从自动发现取默认扫描曲线；
  // findings 未返回（null）时先等它，避免默认到字母序第一个指标
  useEffect(() => {
    if (!batch?.summary || !TERMINAL.has(batch.status) || sweepSel !== null) return
    if (findings === null) return
    const auto = defaultSweepSelection(batch.summary, batch.grid, findings.findings)
    if (auto) setSweepSel({ param: auto.param, metric: auto.metric })
  }, [batch, findings, sweepSel])

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
  const retryN = Math.max(0, Number(retries) || 0)
  const totalItems = comboCount * repeatN
  const problem = batchSubmitProblem(limits, { name, totalItems, repeats: repeatN, retries: retryN })

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
        max_retries: retryN,
        per_run_wall_seconds: Math.max(1, Number(wallSec) || 60),
      })
      setBatch(b)
      // 新批量的 items 尚未产生；不清空会把上一个批量的明细继续显示在下面
      setItems([])
      setItemsTotal(0)
      setItemStatus('')
      setItemDetail(null)
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
    setSweepSel(null)
    try {
      const b = await api.getBatch(id)
      setBatch(b)
      setFindings(null)
      setItemStatus('')
      setItemDetail(null)
      if (TERMINAL.has(b.status)) {
        const page = await api.listBatchItems(id, ITEMS_PAGE_SIZE)
        setItems(page.items)
        setItemsTotal(page.total)
        api.getBatchFindings(id).then(setFindings).catch(() => {})
      } else {
        setItems([])
        setItemsTotal(0)
      }
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

  async function retryFailed() {
    if (!batch) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const b = await api.retryBatch(batch.id)
      setBatch(b)
      setNotice(`已提交批量 #${b.id} 的失败项重试。`)
      refreshBatches()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function retryBatchRow(b: BatchListItem) {
    if (!window.confirm(`重试批量 #${b.id}「${b.name}」的失败项？已完成项不会重跑。`)) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const updated = await api.retryBatch(b.id)
      if (batch?.id === b.id) setBatch(updated)
      setNotice(`已提交批量 #${b.id} 的失败项重试。`)
      refreshBatches()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  function useAsTemplate() {
    if (!batch) return
    onUseTemplate?.(batch.spec)
    setRows(gridRowsFromBatch(batch.grid))
    setRepeats(String(batch.repeats))
    setStrategy(batch.seed_strategy)
    setRetries(String(batch.max_retries ?? 0))
    setWallSec(String(batch.per_run_wall_seconds ?? 60))
    setName(`${batch.name}（副本）`.slice(0, limits.nameMaxLength))
    setNotice(`已按批量 #${batch.id} 的配置填充表单（未启动）；可调整后重新启动。`)
  }

  async function cancelBatchRow(b: BatchListItem) {    if (!window.confirm(`取消批量 #${b.id}「${b.name}」正在进行的运行？`)) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await api.cancelBatch(b.id)
      setNotice(`已取消批量 #${b.id} 的运行。`)
      refreshBatches()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function removeBatch(b: BatchListItem) {
    if (!window.confirm(`删除批量 #${b.id}「${b.name}」及其全部单项结果？此操作不可撤销。`)) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await api.deleteBatch(b.id)
      setBatches((list) => list.filter((x) => x.id !== b.id))
      setBatchesTotal((n) => Math.max(0, n - 1))
      // 正在查看的就是被删批量时立即收起，避免继续展示已不存在的数据
      if (batch?.id === b.id) {
        setBatch(null)
        setItems([])
        setItemsTotal(0)
        setFindings(null)
        setSweepSel(null)
        setItemDetail(null)
      }
      setNotice(`已删除批量 #${b.id}「${b.name}」及其单项结果。`)
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
  const sweepParams = batch ? sweepParamOptions(batch.summary, batch.grid) : []
  const sweepMetrics = batch && sweepSel ? sweepMetricOptions(batch.summary, sweepSel.param) : []
  const sweep =
    batch?.summary && sweepSel ? buildSweep(batch.summary, batch.grid, sweepSel.param, sweepSel.metric) : null

  return (
    <>
      {error && (
        <p
          role="alert"
          style={{ color: '#dc2626', background: '#fef2f2', padding: '6px 10px', borderRadius: 6, fontSize: 13 }}
        >
          错误：{error}
        </p>
      )}
      {notice && <p role="status" style={{ color: '#166534', fontSize: 13 }}>{notice}</p>}
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
            {problem && <strong style={{ color: '#dc2626' }}>（{problem}）</strong>}
          </p>
          <p style={{ fontSize: 12, color: '#6b7280' }}>
            网格键只能是模型的<strong>顶层参数名</strong>；嵌套字段（如到达/服务过程的子项）
            不支持点号路径，请先在上方参数面板设好，再用平铺参数做扫描。
          </p>
        </div>
        <div style={{ flex: 1, minWidth: 220 }}>
          <label style={rowFlex}>
            批量名称：
            <input value={name} onChange={(e) => setName(e.target.value)} style={control} />
          </label>
          <label style={rowFlex}>
            每组重复：
            <input
              type="number"
              min={limits.repeatsMin}
              max={limits.repeatsMax}
              value={repeats}
              onChange={(e) => setRepeats(e.target.value)}
              style={control}
            />
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
            <input
              type="number"
              min={limits.retriesMin}
              max={limits.retriesMax}
              value={retries}
              onChange={(e) => setRetries(e.target.value)}
              style={control}
            />
          </label>
          <label style={rowFlex}>
            单项墙钟（秒）：
            <input value={wallSec} onChange={(e) => setWallSec(e.target.value)} style={control} />
          </label>
          <button onClick={submit} disabled={busy || !!problem} style={primaryBtn}>
            启动批量实验
          </button>
          <p style={{ fontSize: 12, color: '#6b7280' }}>
            使用上方「模型与参数」中的当前配置作为基础 spec；网格参数在其之上做笛卡尔积。
          </p>
        </div>
      </div>

      {(batches.length > 0 || batchesTotal > 0 || filterModel || filterStatus) && (
        <>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', margin: '12px 0 4px' }}>
            <label style={{ ...rowFlex, margin: 0 }}>
              模型：
              <select
                value={filterModel}
                onChange={(e) => changeBatchModel(e.target.value)}
                aria-label="按模型筛选批量"
                style={{ ...smallBtn, padding: '4px 8px' }}
              >
                <option value="">全部模型</option>
                {models.map((m) => (
                  <option key={m.model_id} value={m.model_id}>
                    {m.display_name}
                  </option>
                ))}
              </select>
            </label>
            <label style={{ ...rowFlex, margin: 0 }}>
              状态：
              <select
                value={filterStatus}
                onChange={(e) => changeBatchStatus(e.target.value)}
                aria-label="按状态筛选批量"
                style={{ ...smallBtn, padding: '4px 8px' }}
              >
                <option value="">全部状态</option>
                {BATCH_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {statusLabel(s)}
                  </option>
                ))}
              </select>
            </label>
            {(filterModel || filterStatus) && (
              <button onClick={clearBatchFilters} style={smallBtn}>
                清除筛选
              </button>
            )}
          </div>
          {(filterModel || filterStatus) && (
            <p role="status" style={{ fontSize: 12, color: '#92400e', margin: '0 0 4px' }}>
              筛选：{filterModel ? `模型 ${filterModel}` : ''}
              {filterModel && filterStatus ? ' · ' : ''}
              {filterStatus ? `状态 ${statusLabel(filterStatus)}` : ''}（只统计符合条件的批量）
            </p>
          )}
          {batches.length > 0 ? (
            <>
          <h4 style={{ fontSize: 14, margin: '12px 0 4px' }}>{batchesHeading(batches.length, batchesTotal)}</h4>
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
                <td style={td}>{modelVersionLabel(b.model_id, b.model_version)}</td>
                <td style={td}>{statusLabel(b.status)}</td>
                <td style={td}>
                  {b.done_items}/{b.total_items}
                  {b.failed_items > 0 ? `（失败 ${b.failed_items}）` : ''}
                </td>
                <td style={td}>
                  <button onClick={() => openBatch(b.id)} disabled={busy} style={{ ...smallBtn, padding: '4px 10px' }}>
                    查看
                  </button>{' '}
                  {canCancelBatch(b.status) && (
                    <>
                      <button
                        onClick={() => cancelBatchRow(b)}
                        disabled={busy}
                        aria-label={`取消批量 ${b.id} 的运行`}
                        style={{ ...smallBtn, padding: '4px 10px', color: '#b45309', borderColor: '#fde68a' }}
                      >
                        取消
                      </button>{' '}
                    </>
                  )}
                  {canRetryFailed(b.status, b.failed_items) && (
                    <>
                      <button
                        onClick={() => retryBatchRow(b)}
                        disabled={busy}
                        aria-label={`重试批量 ${b.id} 的失败项（列表）`}
                        style={{ ...smallBtn, padding: '4px 10px', color: '#1d4ed8', borderColor: '#bfdbfe' }}
                      >
                        重试
                      </button>{' '}
                    </>
                  )}
                  <button
                    onClick={() => removeBatch(b)}
                    disabled={busy}
                    aria-label={`删除批量 ${b.id}`}
                    title={b.status === 'running' ? '运行中的批量需先取消再删除' : '删除批量及其全部单项结果'}
                    style={{ ...smallBtn, padding: '4px 10px', color: '#b91c1c', borderColor: '#fecaca' }}
                  >
                    删除
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
          </table>
          {batches.length < batchesTotal && (
            <button onClick={loadMoreBatches} disabled={busy} style={{ ...smallBtn, marginTop: 8 }}>
              {moreLabel(batches.length, batchesTotal)}
            </button>
          )}
            </>
          ) : (
            <p style={{ color: '#6b7280', fontSize: 13 }}>没有符合当前筛选条件的批量。</p>
          )}
        </>
      )}

      {batch !== null && (
        <div style={{ marginTop: 16, borderTop: '1px dashed #d1d5db', paddingTop: 12 }}>
          <p style={{ fontSize: 13, color: '#374151' }}>
            批量 #{batch.id}「{batch.name}」 · 模型 {batch.model_id} v{batch.model_version} · 状态{' '}
            <strong role="status">{statusLabel(batch.status)}</strong> · 种子策略 {batch.seed_strategy}（基种子 {batch.seed_base ?? '—'}）
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
            {canRetryFailed(batch.status, batch.counts.failed ?? 0) && (
              <button
                onClick={retryFailed}
                disabled={busy}
                aria-label={`重试批量 ${batch.id} 的失败项`}
                style={{ ...smallBtn, color: '#1d4ed8', borderColor: '#bfdbfe' }}
              >
                重试失败项（{batch.counts.failed}）
              </button>
            )}
            <button
              onClick={useAsTemplate}
              disabled={busy}
              aria-label={`以批量 ${batch.id} 为模板`}
              style={smallBtn}
            >
              以该批量为模板
            </button>
            <a
              href={api.batchCsvUrl(batch.id)}
              download={`worldlab-batch-${batch.id}.csv`}
              aria-label={`导出批量 ${batch.id} 的 CSV`}
              style={{ ...smallBtn, textDecoration: 'none', display: 'inline-block' }}
            >
              导出 CSV
            </a>
            <a
              href={api.batchReportUrl(batch.id, 'markdown')}
              download={`worldlab-batch-${batch.id}.md`}
              aria-label={`导出批量 ${batch.id} 的 Markdown 报告`}
              style={{ ...smallBtn, textDecoration: 'none', display: 'inline-block' }}
            >
              报告MD
            </a>
            <a
              href={api.batchReportUrl(batch.id, 'json')}
              download={`worldlab-batch-${batch.id}.json`}
              aria-label={`导出批量 ${batch.id} 的 JSON 报告`}
              style={{ ...smallBtn, textDecoration: 'none', display: 'inline-block' }}
            >
              报告JSON
            </a>
          </div>
          {Object.keys(batch.counts).length > 0 && (
            <p style={{ fontSize: 12, color: '#6b7280' }}>
              {Object.entries(batch.counts)
                .map(([k, v]) => `${k}: ${v}`)
                .join(' · ')}
            </p>
          )}
          {batch.error && <p role="alert" style={{ color: '#dc2626', fontSize: 13 }}>批量错误：{batch.error}</p>}

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
              {findings && (
                <>
                  <h4 style={{ fontSize: 14, marginBottom: 4 }}>自动发现（临界点与离散异常）</h4>
                  {findings.findings.length === 0 ? (
                    <p style={{ fontSize: 13, color: '#6b7280', margin: '4px 0' }}>
                      这批结果里没有发现显著跳变或离散异常。
                    </p>
                  ) : (
                    <ul style={{ fontSize: 13, margin: '4px 0', paddingLeft: 20 }}>
                      {findings.findings.map((f, i) => (
                        <li key={i}>
                          {f.type === 'jump' ? (
                            <button
                              style={linkBtn}
                              title="点击查看该跳变的扫描曲线"
                              onClick={() => setSweepSel({ param: f.param, metric: f.metric })}
                            >
                              {formatFinding(f)}
                            </button>
                          ) : (
                            formatFinding(f)
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                  <p style={{ fontSize: 12, color: '#6b7280', margin: '2px 0 8px' }}>{findings.note}</p>
                </>
              )}
              {sweepParams.length > 0 && (
                <>
                  <h4 style={{ fontSize: 14, marginBottom: 4 }}>扫描曲线（指标均值 vs 参数）</h4>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', margin: '6px 0', flexWrap: 'wrap' }}>
                    <label style={{ fontSize: 13 }}>
                      参数{' '}
                      <select
                        aria-label="扫描参数"
                        value={sweepSel?.param ?? ''}
                        onChange={(e) => {
                          const p = e.target.value
                          const ms = sweepMetricOptions(batch!.summary, p)
                          setSweepSel({ param: p, metric: ms[0] ?? '' })
                        }}
                        style={control}
                      >
                        {sweepParams.map((p) => (
                          <option key={p} value={p}>
                            {p}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label style={{ fontSize: 13 }}>
                      指标{' '}
                      <select
                        aria-label="扫描指标"
                        value={sweepSel?.metric ?? ''}
                        onChange={(e) => sweepSel && setSweepSel({ ...sweepSel, metric: e.target.value })}
                        style={control}
                      >
                        {sweepMetrics.map((m) => (
                          <option key={m} value={m}>
                            {m}
                          </option>
                        ))}
                      </select>
                    </label>
                    {sweep && Object.keys(sweep.others).length > 0 && (
                      <span style={{ fontSize: 12, color: '#6b7280' }}>
                        其余参数固定 {JSON.stringify(sweep.others)}
                      </span>
                    )}
                  </div>
                  {sweep ? (
                    <SweepChart sweep={sweep} />
                  ) : (
                    <p style={{ fontSize: 13, color: '#6b7280' }}>当前切片可用数据点不足，无法画曲线。</p>
                  )}
                </>
              )}
            </>
          )}

          {batch && TERMINAL.has(batch.status) && (
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center', margin: '8px 0' }}>
              <label style={{ ...rowFlex, margin: 0 }}>
                单项状态：
                <select
                  value={itemStatus}
                  onChange={(e) => void changeItemStatus(e.target.value)}
                  disabled={busy}
                  aria-label="按状态筛选单项"
                  style={{ ...smallBtn, padding: '4px 8px' }}
                >
                  <option value="">全部状态</option>
                  {ITEM_STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {statusLabel(s)}
                    </option>
                  ))}
                </select>
              </label>
              {itemStatus && (
                <span style={{ fontSize: 12, color: '#92400e' }}>
                  筛选：{statusLabel(itemStatus)}（共 {itemsTotal} 项）
                </span>
              )}
            </div>
          )}
          {batch && TERMINAL.has(batch.status) && itemStatus && items.length === 0 && (
            <p style={{ color: '#6b7280', fontSize: 13 }}>
              没有状态为「{statusLabel(itemStatus)}」的单项。
            </p>
          )}
          {items.length > 0 && (
            <>
              <h4 style={{ fontSize: 14, marginBottom: 4 }}>{itemsHeading(items.length, itemsTotal)}</h4>
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
                      <th style={th}>详情</th>
                      <th style={th}>指标</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((it) => (
                      <tr key={it.id}>
                        <td style={td}>{it.item_index}</td>
                        <td style={{ ...td, fontFamily: 'monospace', fontSize: 12 }}>{JSON.stringify(it.params)}</td>
                        <td style={td}>{it.seed}</td>
                        <td style={td}>{statusLabel(it.status)}</td>
                        <td style={td}>{it.attempts}</td>
                        <td style={td}>{it.steps ?? '—'}</td>
                        <td style={td}>
                          <button
                            onClick={() => setItemDetail(it)}
                            aria-label={`查看批单项 ${it.item_index} 的详情`}
                            style={{ ...smallBtn, padding: '2px 8px', fontSize: 11 }}
                          >
                            详情
                          </button>
                        </td>
                        <td style={{ ...td, fontFamily: 'monospace', fontSize: 12 }}>
                          {it.metrics ? JSON.stringify(it.metrics) : it.error || '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {itemDetail && (
                <div
                  aria-label="批单项详情"
                  style={{ border: '1px solid #d1d5db', borderRadius: 6, padding: '8px 12px', marginTop: 8, background: 'white' }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                    <h4 style={{ fontSize: 14, margin: '2px 0' }}>批单项 #{itemDetail.item_index} 详情</h4>
                    <button
                      onClick={() => setItemDetail(null)}
                      aria-label="关闭批单项详情"
                      style={{ ...smallBtn, padding: '2px 8px' }}
                    >
                      关闭
                    </button>
                  </div>
                  <p style={{ fontSize: 12, color: '#374151', margin: '2px 0' }}>
                    {statusLabel(itemDetail.status)} · 组合 {JSON.stringify(itemDetail.params)} · 重复{' '}
                    {itemDetail.repeat_index} · seed {itemDetail.seed} · 尝试 {itemDetail.attempts}
                  </p>
                  <p style={{ fontSize: 12, color: '#374151', margin: '2px 0' }}>
                    步数 {itemDetail.steps ?? '—'} · 模拟时间{' '}
                    {itemDetail.sim_time != null ? itemDetail.sim_time.toFixed(3) : '—'} · 耗时{' '}
                    {itemDetail.duration_ms != null ? `${(itemDetail.duration_ms / 1000).toFixed(2)} s` : '—'}
                  </p>
                  <p style={{ fontSize: 11, color: '#6b7280', margin: '2px 0', wordBreak: 'break-all' }}>
                    结果 SHA-256：{itemDetail.result_sha256 ?? '—'}
                  </p>
                  {itemDetail.error && (
                    <p role="alert" style={{ color: '#b91c1c', fontSize: 12, margin: '2px 0' }}>
                      错误：{itemDetail.error}
                    </p>
                  )}
                  <p style={{ fontSize: 12, color: '#374151', margin: '6px 0 2px' }}>指标：</p>
                  <pre style={{ margin: 0, fontSize: 11, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    {itemDetail.metrics ? JSON.stringify(itemDetail.metrics, null, 2) : '（无）'}
                  </pre>
                </div>
              )}
              {moreLabel(items.length, itemsTotal) && (
                <button onClick={loadMoreItems} disabled={busy} style={{ ...smallBtn, marginTop: 8 }}>
                  {moreLabel(items.length, itemsTotal)}
                </button>
              )}
            </>
          )}
        </div>
      )}
    </>
  )
}

const rowFlex: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: 8, margin: '6px 0' }
const linkBtn: React.CSSProperties = {
  border: 'none',
  background: 'none',
  padding: 0,
  font: 'inherit',
  color: '#1d4ed8',
  cursor: 'pointer',
  textAlign: 'left',
  textDecoration: 'underline',
  textUnderlineOffset: 3,
}

function SweepChart({ sweep }: { sweep: SweepSelection }) {
  const width = 640
  const height = 180
  const canvasRef = useCanvas(
    (ctx, w, h) => drawLineChart(ctx, { width: w, height: h, series: [sweep.series], band: sweep.band }),
    width,
    height,
  )
  return (
    <div>
      <canvas
        ref={canvasRef}
        style={{ maxWidth: '100%', border: '1px solid #d1d5db', borderRadius: 4 }}
        role="img"
        aria-label={
          sweep.band
            ? `${sweep.param} 与 ${sweep.metric} 的扫描曲线（蓝线为均值，阴影为 95% 置信区间带）`
            : `${sweep.param} 与 ${sweep.metric} 的扫描曲线（重复次数不足，无置信带）`
        }
      />
      <p style={{ fontSize: 12, color: '#6b7280', margin: '4px 0' }}>
        {sweep.band
          ? '阴影带为各点 95% 置信区间（正态近似，来自该组合的全部重复）；带越宽说明重复间波动越大。'
          : '每个参数值只做 1 次重复（或波动为 0）时给不出置信带——把「每组重复」调到 ≥2 再看。'}
      </p>
    </div>
  )
}
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
