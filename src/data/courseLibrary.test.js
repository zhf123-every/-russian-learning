import { describe, it, expect } from 'vitest'
import { courseLibrary, LEVELS, findVideo, getLevelVideos } from './courseLibrary'

describe('courseLibrary', () => {
  it('has all four levels non-empty', () => {
    for (const l of LEVELS) {
      expect(courseLibrary[l], l).toBeTruthy()
      expect(courseLibrary[l].collections.length, l).toBeGreaterThan(0)
    }
  })

  it('every video has a non-empty id/title and >=15 sentences', () => {
    for (const l of LEVELS) {
      for (const c of courseLibrary[l].collections) {
        for (const v of c.videos) {
          expect(v.id).toBeTruthy()
          expect(v.title).toBeTruthy()
          expect(v.sentences.length).toBeGreaterThanOrEqual(15)
          for (const s of v.sentences) {
            expect(s.id).toBeTruthy()
            expect(s.russian.trim()).not.toBe('')
            expect(s.chinese.trim()).not.toBe('')
          }
        }
      }
    }
  })

  it('video ids are globally unique', () => {
    const ids = []
    for (const l of LEVELS) for (const c of courseLibrary[l].collections) for (const v of c.videos) ids.push(v.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('findVideo resolves an existing id with level + collection', () => {
    const first = getLevelVideos('A1')[0]
    const r = findVideo(first.video.id)
    expect(r.video.id).toBe(first.video.id)
    expect(r.level).toBe('A1')
    expect(r.collection).toBeTruthy()
  })

  it('findVideo returns null for unknown id', () => {
    expect(findVideo('nope')).toBeNull()
  })
})
