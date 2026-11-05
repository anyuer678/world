/** 后端 status 是稳定的英文枚举（契约面），面向用户的中文名统一在这里翻译。
 *
 * 会话、实验、批量、批单项共用同一套枚举；未知值原样返回——静默吞掉新状态
 * 比显示英文原文更难排查。R45：此前只有会话状态经过翻译，批量与实验历史
 * 直接显示 `completed`/`cancelled`。 */
const STATUS_LABELS: Record<string, string> = {
  idle: '就绪',
  created: '已创建',
  queued: '排队中',
  pending: '等待中',
  running: '运行中',
  paused: '已暂停',
  completed: '已完成',
  cancelled: '已取消',
  failed: '失败',
  error: '出错',
  step_limit: '达步数上限',
  wall_timeout: '超时',
}

export function statusLabel(s: string): string {
  return STATUS_LABELS[s] ?? s
}
