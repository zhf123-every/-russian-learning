import { describe, it, expect, beforeEach } from 'vitest'
import { useCourseStore } from './courseStore'

const reset = () => useCourseStore.setState({ progress: {}, recent: [], materials: [] })

describe('courseStore', () => {
  beforeEach(() => { localStorage.clear(); reset() })

  it('getVideo resolves a course video', () => {
    const v = useCourseStore.getState().getVideo('a1_greet_01')
    expect(v.id).toBe('a1_greet_01')
  })

  it('getVideo resolves a custom material and returns null otherwise', () => {
    useCourseStore.getState().addMaterial({ id: 'custom_x', title: 't', sentences: [], createdAt: 1 })
    expect(useCourseStore.getState().getVideo('custom_x').title).toBe('t')
    expect(useCourseStore.getState().getVideo('nope')).toBeNull()
  })

  it('pushRecent dedupes and caps at 10', () => {
    const s = useCourseStore.getState()
    for (let i = 0; i < 12; i++) s.pushRecent('v' + i)
    s.pushRecent('v0')
    const { recent } = useCourseStore.getState()
    expect(recent.length).toBe(10)
    expect(recent[0].videoId).toBe('v0')
    expect(recent.filter(r => r.videoId === 'v0').length).toBe(1)
  })

  it('recordSentenceScore + submitVideo computes score and marks done', () => {
    const s = useCourseStore.getState()
    s.recordSentenceScore('a1_greet_01', 1, { dictate: 100 })
    s.recordSentenceScore('a1_greet_01', 2, { recite: 0 })
    const score = s.submitVideo('a1_greet_01')
    expect(score).toBe(50)
    expect(useCourseStore.getState().progress['a1_greet_01'].done).toBe(true)
  })

  it('resetLevel clears that level progress', () => {
    useCourseStore.setState({ progress: { a1_greet_01: { done: true, score: 90 }, a2_past_01: { done: true, score: 90 } } })
    useCourseStore.getState().resetLevel('A1')
    const p = useCourseStore.getState().progress
    expect(p['a1_greet_01']).toBeUndefined()
    expect(p['a2_past_01']).toBeDefined()
  })
})
