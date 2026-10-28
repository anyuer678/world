export interface NetNode {
  id: string
  x: number
  y: number
}

export interface NetEdge {
  src: string
  dst: string
}

export interface DrawVehicle {
  edge: number
  cell: number
  v: number
}

export interface Network {
  nodes: NetNode[]
  edges: NetEdge[]
}

export function parseNetwork(raw: unknown): Network | null {
  if (raw === null || typeof raw !== 'object') return null
  const nodes = (raw as Record<string, unknown>).nodes
  const edges = (raw as Record<string, unknown>).edges
  if (!Array.isArray(nodes) || !Array.isArray(edges)) return null
  return { nodes: nodes as NetNode[], edges: edges as NetEdge[] }
}

export function computeBounds(net: Network): { minX: number; minY: number; maxX: number; maxY: number } {
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const n of net.nodes) {
    minX = Math.min(minX, n.x)
    minY = Math.min(minY, n.y)
    maxX = Math.max(maxX, n.x)
    maxY = Math.max(maxY, n.y)
  }
  if (!Number.isFinite(minX)) return { minX: 0, minY: 0, maxX: 1, maxY: 1 }
  if (maxX - minX < 1e-9) {
    minX -= 1
    maxX += 1
  }
  if (maxY - minY < 1e-9) {
    minY -= 1
    maxY += 1
  }
  return { minX, minY, maxX, maxY }
}

export function edgeCells(net: Network, e: NetEdge): number {
  const a = net.nodes.find((n) => n.id === e.src)
  const b = net.nodes.find((n) => n.id === e.dst)
  if (!a || !b) return 1
  return Math.max(1, Math.round(Math.hypot(a.x - b.x, a.y - b.y)))
}

export interface DrawOptions {
  width: number
  height: number
  padding?: number
  vehicles?: DrawVehicle[]
  edgeLoad?: number[]
  signalNodes?: { id: string; green: boolean }[]
}

export function drawNetwork(ctx: CanvasRenderingContext2D, net: Network, opts: DrawOptions): void {
  const { width, height } = opts
  const pad = opts.padding ?? 24
  const { minX, minY, maxX, maxY } = computeBounds(net)
  const sx = (x: number) => pad + ((x - minX) / (maxX - minX)) * (width - 2 * pad)
  const sy = (y: number) => pad + ((y - minY) / (maxY - minY)) * (height - 2 * pad)

  ctx.fillStyle = '#f8fafc'
  ctx.fillRect(0, 0, width, height)

  const maxLoad = Math.max(1, ...(opts.edgeLoad ?? [1]))
  net.edges.forEach((e, i) => {
    const a = net.nodes.find((n) => n.id === e.src)
    const b = net.nodes.find((n) => n.id === e.dst)
    if (!a || !b) return
    const load = opts.edgeLoad?.[i] ?? 0
    const ratio = load / maxLoad
    ctx.strokeStyle = ratio > 0.66 ? '#dc2626' : ratio > 0.33 ? '#f59e0b' : '#94a3b8'
    ctx.lineWidth = 2 + ratio * 5
    ctx.beginPath()
    ctx.moveTo(sx(a.x), sy(a.y))
    ctx.lineTo(sx(b.x), sy(b.y))
    ctx.stroke()
    // direction tick: small perpendicular arrow head at 60% of the edge
    const mx = sx(a.x) + (sx(b.x) - sx(a.x)) * 0.6
    const my = sy(a.y) + (sy(b.y) - sy(a.y)) * 0.6
    const dx = sx(b.x) - sx(a.x)
    const dy = sy(b.y) - sy(a.y)
    const len = Math.hypot(dx, dy) || 1
    ctx.fillStyle = '#64748b'
    ctx.beginPath()
    ctx.moveTo(mx + (dx / len) * 5, my + (dy / len) * 5)
    ctx.lineTo(mx + (-dy / len) * 3, my + (dx / len) * 3)
    ctx.lineTo(mx + (dy / len) * 3, my + (-dx / len) * 3)
    ctx.fill()
  })

  for (const n of net.nodes) {
    const sig = opts.signalNodes?.find((s) => s.id === n.id)
    ctx.beginPath()
    ctx.arc(sx(n.x), sy(n.y), sig ? 7 : 5, 0, Math.PI * 2)
    ctx.fillStyle = sig ? (sig.green ? '#16a34a' : '#dc2626') : '#334155'
    ctx.fill()
    if (sig) {
      ctx.strokeStyle = '#1f2937'
      ctx.lineWidth = 1.5
      ctx.stroke()
    }
  }

  for (const v of opts.vehicles ?? []) {
    const e = net.edges[v.edge]
    if (!e) continue
    const a = net.nodes.find((n) => n.id === e.src)
    const b = net.nodes.find((n) => n.id === e.dst)
    if (!a || !b) continue
    const cells = edgeCells(net, e)
    const t = Math.min(1, v.cell / cells)
    ctx.fillStyle = v.v === 0 ? '#b91c1c' : '#2563eb'
    ctx.beginPath()
    ctx.arc(sx(a.x + (b.x - a.x) * t), sy(a.y + (b.y - a.y) * t), 3.5, 0, Math.PI * 2)
    ctx.fill()
  }
}
