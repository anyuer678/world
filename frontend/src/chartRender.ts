export interface Series {
  name: string
  color: string
  data: [number, number][]
}

export interface LineChartOptions {
  width: number
  height: number
  series: Series[]
  yMax?: number
  emptyText?: string
}

export interface Bounds {
  xMin: number
  xMax: number
  yMin: number
  yMax: number
}

export function seriesBounds(series: Series[]): Bounds {
  let xMin = Infinity
  let xMax = -Infinity
  let yMin = Infinity
  let yMax = -Infinity
  for (const s of series) {
    for (const [x, y] of s.data) {
      xMin = Math.min(xMin, x)
      xMax = Math.max(xMax, x)
      yMin = Math.min(yMin, y)
      yMax = Math.max(yMax, y)
    }
  }
  if (!Number.isFinite(xMin)) return { xMin: 0, xMax: 1, yMin: 0, yMax: 1 }
  if (xMax - xMin < 1e-9) xMax = xMin + 1
  if (yMax - yMin < 1e-9) yMax = yMin + 1
  return { xMin, xMax, yMin: Math.min(yMin, 0), yMax }
}

export function niceMax(v: number): number {
  if (!Number.isFinite(v) || v <= 0) return 1
  const exp = Math.floor(Math.log10(v))
  const base = Math.pow(10, exp)
  const mant = v / base
  const nice = mant <= 1 ? 1 : mant <= 2 ? 2 : mant <= 5 ? 5 : 10
  return nice * base
}

export function fmtTick(v: number): string {
  if (Math.abs(v) >= 100000) return `${(v / 1000).toFixed(0)}k`
  return Number.isInteger(v) ? String(v) : v.toFixed(1)
}

const PAD = { top: 12, right: 12, bottom: 22, left: 44 }

export function drawLineChart(ctx: CanvasRenderingContext2D, opts: LineChartOptions): void {
  const { width, height, series } = opts
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, width, height)

  const hasData = series.some((s) => s.data.length > 0)
  if (!hasData) {
    ctx.fillStyle = '#9ca3af'
    ctx.font = '12px sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText(opts.emptyText ?? '暂无数据', width / 2, height / 2)
    return
  }

  const b = seriesBounds(series)
  const yMax = niceMax(opts.yMax ?? b.yMax)
  const plotW = width - PAD.left - PAD.right
  const plotH = height - PAD.top - PAD.bottom
  const toX = (x: number) => PAD.left + ((x - b.xMin) / (b.xMax - b.xMin)) * plotW
  const toY = (y: number) => PAD.top + plotH - (Math.max(0, Math.min(y, yMax)) / yMax) * plotH

  ctx.strokeStyle = '#e5e7eb'
  ctx.lineWidth = 1
  ctx.fillStyle = '#6b7280'
  ctx.font = '10px sans-serif'
  ctx.textAlign = 'right'
  for (let i = 0; i <= 4; i++) {
    const v = (yMax / 4) * i
    const y = toY(v)
    ctx.beginPath()
    ctx.moveTo(PAD.left, y)
    ctx.lineTo(width - PAD.right, y)
    ctx.stroke()
    ctx.fillText(fmtTick(v), PAD.left - 6, y + 3)
  }

  ctx.textAlign = 'center'
  for (let i = 0; i <= 2; i++) {
    const x = b.xMin + ((b.xMax - b.xMin) * i) / 2
    ctx.fillText(fmtTick(x), toX(x), height - 6)
  }
  ctx.strokeStyle = '#9ca3af'
  ctx.strokeRect(PAD.left, PAD.top, plotW, plotH)

  for (const s of series) {
    if (s.data.length === 0) continue
    ctx.strokeStyle = s.color
    ctx.lineWidth = 1.5
    ctx.beginPath()
    s.data.forEach(([x, y], i) => {
      const px = toX(x)
      const py = toY(y)
      if (i === 0) ctx.moveTo(px, py)
      else ctx.lineTo(px, py)
    })
    ctx.stroke()
  }

  let lx = width - PAD.right
  for (let i = series.length - 1; i >= 0; i--) {
    const s = series[i]
    ctx.fillStyle = s.color
    ctx.fillRect(lx - 10, 2, 8, 8)
    ctx.fillStyle = '#374151'
    ctx.textAlign = 'right'
    ctx.font = '11px sans-serif'
    ctx.fillText(s.name, lx - 14, 10)
    lx -= 14 + ctx.measureText(s.name).width
  }
}

export function ganttRows(segments: [number, number, number][], maxRows = 16): number[] {
  const lastEnd = new Map<number, number>()
  for (const [, e, q] of segments) {
    lastEnd.set(q, Math.max(lastEnd.get(q) ?? -Infinity, e))
  }
  return [...lastEnd.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, maxRows)
    .map(([q]) => q)
    .sort((a, b) => a - b)
}

export function ganttExtent(segments: [number, number, number][]): { tMin: number; tMax: number } {
  if (segments.length === 0) return { tMin: 0, tMax: 1 }
  let tMin = Infinity
  let tMax = -Infinity
  for (const [s, e] of segments) {
    tMin = Math.min(tMin, s)
    tMax = Math.max(tMax, e)
  }
  if (tMax - tMin < 1e-9) tMax = tMin + 1
  return { tMin, tMax }
}

export const GANTT_PALETTE = [
  '#2563eb', '#f59e0b', '#10b981', '#ef4444',
  '#8b5cf6', '#06b6d4', '#f97316', '#84cc16',
]

const ROW_H = 16

export interface GanttOptions {
  width: number
  height: number
  segments: [number, number, number][]
  rows?: number[]
}

export function drawGantt(ctx: CanvasRenderingContext2D, opts: GanttOptions): void {
  const { width, height } = opts
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, width, height)

  const segments = opts.segments
  if (segments.length === 0) {
    ctx.fillStyle = '#9ca3af'
    ctx.font = '12px sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText('暂无运行记录', width / 2, height / 2)
    return
  }

  const rows = opts.rows ?? ganttRows(segments)
  const shown = new Set(rows)
  const visible = segments.filter(([, , q]) => shown.has(q))
  const { tMin, tMax } = ganttExtent(visible)
  const padLeft = 44
  const padBottom = 18
  const plotW = width - padLeft - 8
  const rowH = rows.length > 0 ? Math.min(ROW_H, (height - 20 - padBottom) / rows.length) : ROW_H
  const toX = (t: number) => padLeft + ((t - tMin) / (tMax - tMin)) * plotW

  ctx.font = '10px sans-serif'
  ctx.textAlign = 'right'
  for (let i = 0; i < rows.length; i++) {
    const y = 6 + i * rowH
    ctx.fillStyle = '#f3f4f6'
    ctx.fillRect(padLeft, y, plotW, rowH - 2)
    ctx.fillStyle = '#6b7280'
    ctx.fillText(`#${rows[i]}`, padLeft - 6, y + rowH / 2 + 1)
  }

  for (const [s, e, q] of visible) {
    const rowIdx = rows.indexOf(q)
    if (rowIdx < 0) continue
    const x0 = Math.max(padLeft, toX(s))
    const x1 = Math.max(x0, toX(e))
    ctx.fillStyle = GANTT_PALETTE[q % GANTT_PALETTE.length]
    ctx.fillRect(x0, 6 + rowIdx * rowH, Math.max(1, x1 - x0), rowH - 2)
  }

  ctx.fillStyle = '#6b7280'
  ctx.textAlign = 'center'
  ctx.fillText(fmtTick(tMin), padLeft, height - 4)
  ctx.fillText(fmtTick((tMin + tMax) / 2), padLeft + plotW / 2, height - 4)
  ctx.fillText(fmtTick(tMax), width - 8, height - 4)
}

export interface AccessRun {
  hit: boolean
  count: number
}

export function runsFromBits(bits: number[]): AccessRun[] {
  const runs: AccessRun[] = []
  for (const b of bits) {
    const hit = b === 1
    const last = runs[runs.length - 1]
    if (last && last.hit === hit) last.count += 1
    else runs.push({ hit, count: 1 })
  }
  return runs
}

export interface AccessStripOptions {
  width: number
  height: number
  bits: number[]
}

export function drawAccessStrip(ctx: CanvasRenderingContext2D, opts: AccessStripOptions): void {
  const { width, height } = opts
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, width, height)

  if (opts.bits.length === 0) {
    ctx.fillStyle = '#9ca3af'
    ctx.font = '12px sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText('暂无访问', width / 2, height / 2)
    return
  }

  const trackH = Math.min(18, height - 8)
  const y = (height - trackH) / 2
  ctx.fillStyle = '#f3f4f6'
  ctx.fillRect(2, y, width - 4, trackH)

  const runs = runsFromBits(opts.bits)
  const total = opts.bits.length
  let acc = 0
  for (const r of runs) {
    const x0 = 2 + (acc / total) * (width - 4)
    const w = Math.max(1, (r.count / total) * (width - 4))
    ctx.fillStyle = r.hit ? '#22c55e' : '#ef4444'
    ctx.fillRect(x0, y, w, trackH)
    acc += r.count
  }
}
