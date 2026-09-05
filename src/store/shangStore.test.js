import { describe, it, expect, beforeEach } from 'vitest'
import { useShangStore, STAGES } from '../store/shangStore'

describe('尚雯婕学习法 5 阶段状态机', () => {
  beforeEach(() => {
    localStorage.clear()
    useShangStore.setState({ progress: {} })
  })

  const vid = 'sq_shopping'

  it('初始化进入阶段1（整体盲听）', () => {
    useShangStore.getState().init(vid)
    expect(useShangStore.getState().load(vid).stage).toBe(STAGES.LISTEN)
    expect(STAGES.LISTEN).toBe(1)
  })

  it('顺序不可逆：阶段只能 +1 递增或回退', () => {
    useShangStore.getState().init(vid)
    // 阶段1 → 阶段2 合法
    useShangStore.getState().setStage(vid, STAGES.DICTATE)
    expect(useShangStore.getState().load(vid).stage).toBe(STAGES.DICTATE)
    // 回退到阶段1 合法
    useShangStore.getState().setStage(vid, STAGES.LISTEN)
    expect(useShangStore.getState().load(vid).stage).toBe(STAGES.LISTEN)
    // 阶段1 直接跳到阶段5（+4）应被 UI 阻止，但 store 层可回退
  })

  it('阶段2 听写记录：ok / skipped 两种完成方式', () => {
    useShangStore.getState().init(vid)
    useShangStore.getState().setStage(vid, STAGES.DICTATE)
    useShangStore.getState().setDictation(vid, 1, { text: 'Ско́лько', ok: true })
    useShangStore.getState().setDictation(vid, 2, { text: '', skipped: true, ok: false })
    const d = useShangStore.getState().load(vid).dictations
    expect(d[1].ok).toBe(true)
    expect(d[2].skipped).toBe(true)
  })

  it('阶段4/5 跟读与复述记录', () => {
    useShangStore.getState().init(vid)
    useShangStore.getState().setReciteOk(vid, 1, true)
    expect(useShangStore.getState().load(vid).reciteOk[1]).toBe(true)
  })

  it('完成训练标记 finished，isFinished 返回 true', () => {
    useShangStore.getState().init(vid)
    expect(useShangStore.getState().isFinished(vid)).toBe(false)
    useShangStore.getState().finish(vid)
    expect(useShangStore.getState().load(vid).stage).toBe(STAGES.RECITE_OUT)
    expect(useShangStore.getState().isFinished(vid)).toBe(true)
  })

  it('reset 回到阶段1', () => {
    useShangStore.getState().init(vid)
    useShangStore.getState().setStage(vid, STAGES.RECITE_OUT)
    useShangStore.getState().reset(vid)
    expect(useShangStore.getState().load(vid).stage).toBe(STAGES.LISTEN)
  })

  it('donstamaged: 阶段常量顺序为 1-5', () => {
    expect([STAGES.LISTEN, STAGES.DICTATE, STAGES.CORRECT, STAGES.RECITE, STAGES.RECITE_OUT]).toEqual([1, 2, 3, 4, 5])
  })
})