import { createEmptyCard, fsrs, Rating } from 'ts-fsrs'

// 单例调度器：所有卡共用同一套 FSRS 参数
const scheduler = fsrs()

// 四档评分，映射到 ts-fsrs 的 Rating 枚举
// Rating: Manual=0, Again=1, Hard=2, Good=3, Easy=4
export const RATING = {
  again: Rating.Again,
  hard: Rating.Hard,
  good: Rating.Good,
  easy: Rating.Easy,
}

// 新建一张空白卡（state=New，due 即当前时刻）
export function newCard() {
  return createEmptyCard()
}

// 复习一张卡，返回更新后的卡。
// ts-fsrs 的 next() 统一处理 New/Learning/Review 三种状态，
// 返回 { card, log }，其中 card 为新的卡对象。
// 「忘记」(Again) 时把到期时间钳制到当前时刻，让卡留在到期队列中以便立刻重看。
export function review(card, rating) {
  const now = new Date()
  const next = scheduler.next(card, now, rating).card
  if (rating === Rating.Again) return { ...next, due: now }
  return next
}

// 是否到期：now 支持 Date 或时间戳数字
export function isDue(card, now) {
  const t = now instanceof Date ? now.getTime() : now
  return card.due.getTime() <= t
}

// 持久化前把 Date 字段转成 ISO 字符串，避免 JSON 丢失类型
export function serializeCard(card) {
  return {
    ...card,
    due: card.due instanceof Date ? card.due.toISOString() : card.due,
    last_review: card.last_review
      ? (card.last_review instanceof Date ? card.last_review.toISOString() : card.last_review)
      : null,
  }
}

// 从持久化数据恢复 Date 字段
export function deserializeCard(s) {
  return { ...s, due: new Date(s.due), last_review: s.last_review ? new Date(s.last_review) : null }
}
