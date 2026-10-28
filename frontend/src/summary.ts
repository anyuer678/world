export function summarizeMetrics(kind: string, m: Record<string, number>): string[] {
  const out: string[] = []
  const pct = (x: number) => `${(x * 100).toFixed(1)}%`
  const f2 = (x: number) => (typeof x === 'number' ? x.toFixed(2) : '-')
  const has = (k: string) => typeof m[k] === 'number'

  if (kind === 'queue') {
    if (has('utilization')) {
      const rho = m.utilization
      const judge =
        rho >= 0.85 ? '已贴近服务能力极限，队伍会越排越长' : rho <= 0.3 ? '服务能力明显宽裕' : '负载适中'
      out.push(`服务利用率 ${pct(rho)}，${judge}。`)
    }
    if (has('avg_waiting_time')) {
      out.push(`顾客平均等待 ${f2(m.avg_waiting_time)}、平均逗留 ${f2(m.avg_response_time)}。`)
    }
    if (has('drop_rate') && m.drop_rate > 0) {
      out.push(`丢弃率 ${pct(m.drop_rate)}：系统容量不足，有顾客被拒之门外。`)
    }
  } else if (kind === 'cache') {
    if (has('hit_rate')) {
      const h = m.hit_rate
      const judge = h >= 0.7 ? '访问大多被缓存接住' : h >= 0.3 ? '缓存起到了一定作用' : '缓存几乎没帮上忙'
      out.push(`命中率 ${pct(h)}，${judge}。`)
    }
    if (has('avg_cost_per_access')) {
      out.push(`平均每次访问成本 ${f2(m.avg_cost_per_access)}。`)
    }
  } else if (kind === 'ca') {
    if (has('population') && has('generation')) {
      let trend = '种群处于波动中'
      if (has('population_max') && m.population_max > 0) {
        if (m.population >= m.population_max * 0.9) trend = '当前处于或接近历史峰值'
        else if (m.population <= m.population_max * 0.2) trend = '种群已大幅萎缩'
      }
      out.push(`第 ${m.generation} 代存活 ${m.population} 个细胞，${trend}。`)
    }
    if (has('births_total') && has('deaths_total')) {
      out.push(`累计出生 ${m.births_total}、死亡 ${m.deaths_total}。`)
    }
  } else if (kind === 'traffic') {
    if (has('spawned') && has('completed')) {
      const ratio = m.spawned > 0 ? m.completed / m.spawned : 1
      const judge = ratio >= 0.9 ? '路网整体畅通' : ratio >= 0.6 ? '部分车辆仍在路上' : '拥堵明显，大量车辆滞留'
      out.push(`发车 ${m.spawned} 辆、完成 ${m.completed} 辆，${judge}。`)
    }
    if (has('avg_travel_time') && has('avg_wait_ticks')) {
      out.push(`平均行程 ${f2(m.avg_travel_time)} 拍，其中平均等待 ${f2(m.avg_wait_ticks)} 拍。`)
    }
  } else if (kind === 'cpu_schedule') {
    if (has('avg_waiting_time')) {
      out.push(`作业平均等待 ${f2(m.avg_waiting_time)}、平均周转 ${f2(m.avg_turnaround_time)}。`)
    }
    if (has('cpu_utilization')) {
      out.push(`CPU 利用率 ${pct(m.cpu_utilization)}。`)
    }
    if (has('arrived') && has('completed') && m.completed < m.arrived) {
      out.push(`到达 ${m.arrived} 个作业，尚有 ${m.arrived - m.completed} 个未完成。`)
    }
  }
  return out
}
