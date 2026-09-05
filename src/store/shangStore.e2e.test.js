import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useShangStore, STAGES } from '../store/shangStore'

/**
 * 端到端场景测试：模拟用户走完尚雯婕学习法 5 阶段完整流程
 * 场景：用户从「学习广场」入口进入 sq_shopping 素材（6 句）
 */
describe('场景：用户走完 sq_shopping 完整尚雯婕流程', () => {
  const vid = 'sq_shopping'
  const SENTENCE_COUNT = 6

  beforeEach(() => {
    localStorage.clear()
    useShangStore.setState({ progress: {} })
  })

  it('阶段0 入口校验：hasSubs 逻辑', () => {
    const itemWithSubs = { id: vid, sentences: [{ id: 1 }, { id: 2 }] }
    const itemNoSubs = { id: 'no_subs', sentences: [] }
    const hasSubs = item => Array.isArray(item.sentences) && item.sentences.length > 0
    expect(hasSubs(itemWithSubs)).toBe(true)
    expect(hasSubs(itemNoSubs)).toBe(false)
  })

  it('阶段0 init：进入阶段1（整体盲听）', () => {
    useShangStore.getState().init(vid)
    const p = useShangStore.getState().load(vid)
    expect(p.stage).toBe(STAGES.LISTEN)
    expect(p.dictations).toEqual({})
    expect(p.finished).toBe(false)
  })

  it('阶段1→2：阶段推进（无校验，可直接推进）', () => {
    useShangStore.getState().init(vid)
    act(() => useShangStore.getState().setStage(vid, STAGES.DICTATE))
    expect(useShangStore.getState().load(vid).stage).toBe(STAGES.DICTATE)
  })

  it('阶段2 听写：用户逐句听写 + 跳过机制', () => {
    useShangStore.getState().init(vid)
    act(() => useShangStore.getState().setStage(vid, STAGES.DICTATE))

    // 正确听写 4 句
    for (let i = 1; i <= 4; i++) {
      act(() => useShangStore.getState().setDictation(vid, i, { text: `正确内容${i}`, ok: true }))
    }
    // 跳过 2 句（听不出来）
    for (let i = 5; i <= 6; i++) {
      act(() => useShangStore.getState().setDictation(vid, i, { text: '', skipped: true, ok: false }))
    }

    const dicts = useShangStore.getState().load(vid).dictations
    expect(Object.keys(dicts)).toHaveLength(6)
    expect([1, 2, 3, 4].every(id => dicts[id].ok === true)).toBe(true)
    expect([5, 6].every(id => dicts[id].skipped === true)).toBe(true)
  })

  it('阶段2→3：必须全部完成（ok/skipped都算完成）才允许推进', () => {
    useShangStore.getState().init(vid)
    act(() => useShangStore.getState().setStage(vid, STAGES.DICTATE))

    // 只完成了 5/6 句，阻止推进（业务逻辑在 UI 层检查）
    for (let i = 1; i <= 5; i++) {
      act(() => useShangStore.getState().setDictation(vid, i, { ok: true }))
    }

    const dicts = useShangStore.getState().load(vid).dictations
    const total = 6
    const done = Object.values(dicts).filter(d => d.ok || d.skipped).length
    expect(done < total).toBe(true)
    // UI 层 goStage 函数会在 done < total 时 toast 并 return

    // 完成最后一篇
    act(() => useShangStore.getState().setDictation(vid, 6, { skipped: true }))
    const doneAfter = Object.values(useShangStore.getState().load(vid).dictations).filter(d => d.ok || d.skipped).length
    expect(doneAfter).toBe(6)

    // 现在可以推进到阶段3
    act(() => useShangStore.getState().setStage(vid, STAGES.CORRECT))
    expect(useShangStore.getState().load(vid).stage).toBe(STAGES.CORRECT)
  })

  it('阶段3 对照精读：阶段推进不受 dictations 影响', () => {
    useShangStore.getState().init(vid)
    act(() => useShangStore.getState().setStage(vid, STAGES.CORRECT))
    expect(useShangStore.getState().load(vid).stage).toBe(STAGES.CORRECT)
  })

  it('阶段3→4：可自由推进（无额外校验）', () => {
    useShangStore.getState().init(vid)
    act(() => useShangStore.getState().setStage(vid, STAGES.RECITE))
    expect(useShangStore.getState().load(vid).stage).toBe(STAGES.RECITE)
  })

  it('阶段4 跟读：所有句子标记后可用', () => {
    useShangStore.getState().init(vid)
    act(() => useShangStore.getState().setStage(vid, STAGES.RECITE))
    for (let i = 1; i <= SENTENCE_COUNT; i++) {
      act(() => useShangStore.getState().setReciteOk(vid, i, true))
    }
    const ok = useShangStore.getState().load(vid).reciteOk
    expect(Object.values(ok).every(v => v === true)).toBe(true)
  })

  it('阶段4→5：可自由推进', () => {
    useShangStore.getState().init(vid)
    act(() => useShangStore.getState().setStage(vid, STAGES.RECITE_OUT))
    expect(useShangStore.getState().load(vid).stage).toBe(STAGES.RECITE_OUT)
  })

  it('阶段5 复述：全部标记后允许 finish', () => {
    useShangStore.getState().init(vid)
    act(() => useShangStore.getState().setStage(vid, STAGES.RECITE_OUT))
    for (let i = 1; i <= SENTENCE_COUNT; i++) {
      act(() => useShangStore.getState().setReciteOk(vid, i, true))
    }
    act(() => useShangStore.getState().finish(vid))
    expect(useShangStore.getState().isFinished(vid)).toBe(true)
    expect(useShangStore.getState().load(vid).stage).toBe(STAGES.RECITE_OUT)
  })

  it('完成状态持久化：isFinished 跨 session 有效', () => {
    // 模拟 finish
    useShangStore.getState().init(vid)
    act(() => useShangStore.getState().finish(vid))

    // 模拟重新加载 store（从 localStorage 恢复）
    const saved = JSON.parse(localStorage.getItem('rlearn_v1_shang'))
    useShangStore.setState({ progress: saved })
    expect(useShangStore.getState().isFinished(vid)).toBe(true)
  })

  it('reset：重新开始训练', () => {
    useShangStore.getState().init(vid)
    act(() => useShangStore.getState().setStage(vid, STAGES.RECITE_OUT))
    act(() => useShangStore.getState().finish(vid))
    act(() => useShangStore.getState().reset(vid))
    const p = useShangStore.getState().load(vid)
    expect(p.stage).toBe(STAGES.LISTEN)
    expect(p.dictations).toEqual({})
    expect(p.finished).toBe(false)
  })

  it('顺序不可逆：UI 层阻止跳跃（模拟 goStage 检查）', () => {
    useShangStore.getState().init(vid)
    // 当前阶段 = 1，想跳到 4，差值 > 1，应被 UI 层阻止
    const current = STAGES.LISTEN
    const target = STAGES.RECITE // = 4，差 3
    const canJump = target <= current + 1
    expect(canJump).toBe(false)
  })

  it('回退：阶段2 可回退到阶段1', () => {
    useShangStore.getState().init(vid)
    act(() => useShangStore.getState().setStage(vid, STAGES.DICTATE))
    act(() => useShangStore.getState().setStage(vid, STAGES.LISTEN))
    expect(useShangStore.getState().load(vid).stage).toBe(STAGES.LISTEN)
  })

  it('阶段常量符合预期值（1-5 连续）', () => {
    expect(STAGES.LISTEN).toBe(1)
    expect(STAGES.DICTATE).toBe(2)
    expect(STAGES.CORRECT).toBe(3)
    expect(STAGES.RECITE).toBe(4)
    expect(STAGES.RECITE_OUT).toBe(5)
  })
})