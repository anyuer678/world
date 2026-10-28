export interface JumpFinding {
  type: 'jump'
  param: string
  from: number
  to: number
  metric: string
  value_from: number
  value_to: number
  ratio: number | null
}

export interface DispersionFinding {
  type: 'dispersion'
  params: Record<string, unknown>
  metric: string
  cv: number
  n: number
  mean: number
  std: number
}

export type Finding = JumpFinding | DispersionFinding

export interface FindingsResponse {
  findings: Finding[]
  note: string
}

const f4 = (x: number) => (typeof x === 'number' ? Number(x.toFixed(4)).toString() : '-')

export function formatFinding(f: Finding): string {
  if (f.type === 'jump') {
    if (f.ratio === null) {
      const change =
        f.value_to === 0
          ? `从 ${f4(f.value_from)} 坍缩为 0（完全消失）`
          : `从 0 激增到 ${f4(f.value_to)}（从无到有）`
      return `参数 ${f.param} 从 ${f.from} → ${f.to} 时，指标 ${f.metric} ${change}——可能存在临界点`
    }
    const dir = Math.abs(f.value_to) >= Math.abs(f.value_from) ? '跳升' : '坍缩'
    return `参数 ${f.param} 从 ${f.from} → ${f.to} 时，指标 ${f.metric} 从 ${f4(f.value_from)} ${
      dir
    } 到 ${f4(f.value_to)}（约 ${f.ratio} 倍）——可能存在临界点`
  }
  const params = Object.entries(f.params)
    .map(([k, v]) => `${k}=${String(v)}`)
    .join(', ')
  return `在 ${params} 处，指标 ${f.metric} 重复间波动很大（CV ${(f.cv * 100).toFixed(0)}%，n=${f.n}）：结果对随机性敏感，建议增加重复次数或换种子策略`
}
