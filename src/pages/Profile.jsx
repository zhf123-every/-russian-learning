import { LEVELS } from '../data/courseLibrary'
import { useCourseStore } from '../store/courseStore'
import { useVocabStore } from '../store/vocabStore'

export default function Profile() {
  const progress = useCourseStore(s => s.progress)
  const levelMastery = useCourseStore(s => s.levelMastery)
  const isLevelUnlocked = useCourseStore(s => s.isLevelUnlocked)
  const cards = useVocabStore(s => s.cards)

  const doneVideos = Object.values(progress).filter(p => p.done).length
  let practiced = 0
  for (const p of Object.values(progress)) practiced += Object.keys(p.sentenceScores || {}).length

  const days = new Set(Object.values(progress).map(p => new Date(p.updatedAt).toDateString()))
  const streak = days.size

  return (
    <div className="course">
      <h2>📊 学习统计</h2>
      <div className="videos-grid" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(160px,1fr))', marginBottom: 20 }}>
        <div className="card"><div className="score-big">{days.size}</div><div className="hint">学习天数</div></div>
        <div className="card"><div className="score-big">{streak}</div><div className="hint">连续打卡（去重日）</div></div>
        <div className="card"><div className="score-big">{practiced}</div><div className="hint">练习句子数</div></div>
        <div className="card"><div className="score-big">{doneVideos}</div><div className="hint">完成视频数</div></div>
        <div className="card"><div className="score-big">{cards.length}</div><div className="hint">生词总数</div></div>
      </div>

      <h3>各级掌握度</h3>
      {LEVELS.map(l => (
        <div key={l} className="course-item" style={{ cursor: 'default' }}>
          <span className="t">{l}</span>
          <span className="hint">{isLevelUnlocked(l) ? `掌握 ${levelMastery(l)}%` : '🔒 未解锁'}</span>
        </div>
      ))}
    </div>
  )
}
