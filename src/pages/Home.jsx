import { useState } from 'react'
import { LEVELS, getLevelVideos } from '../data/courseLibrary'
import { useCourseStore } from '../store/courseStore'
import VideoCard from '../components/VideoCard'

export default function Home() {
  const [level, setLevel] = useState('A1')
  const [tag, setTag] = useState('')
  const [q, setQ] = useState('')
  const recent = useCourseStore(s => s.recent)
  const getVideo = useCourseStore(s => s.getVideo)
  const levelMastery = useCourseStore(s => s.levelMastery)
  const isLevelUnlocked = useCourseStore(s => s.isLevelUnlocked)

  const allTags = [...new Set(getLevelVideos(level).flatMap(x => x.video.tags))]
  let videos = getLevelVideos(level)
  if (tag) videos = videos.filter(x => x.video.tags.includes(tag))
  if (q) videos = videos.filter(x => x.video.title.toLowerCase().includes(q.toLowerCase()))

  const recentVideos = recent
    .map(r => ({ ...r, video: getVideo(r.videoId) }))
    .filter(r => r.video)

  return (
    <div className="course">
      <div className="course-levels">
        {LEVELS.map(l => (
          <button key={l} className={'btn sm' + (l === level ? ' primary' : '')}
            disabled={!isLevelUnlocked(l)}
            onClick={() => setLevel(l)}>
            {l}{isLevelUnlocked(l) ? ` · 掌握 ${levelMastery(l)}%` : ' 🔒'}
          </button>
        ))}
      </div>

      <div className="row" style={{ marginBottom: 12 }}>
        <input className="qfill" placeholder="🔍 搜索视频标题…" value={q} onChange={e => setQ(e.target.value)} />
      </div>
      <div className="row" style={{ marginBottom: 16 }}>
        {allTags.map(t => (
          <button key={t} className={'btn sm' + (t === tag ? ' primary' : '')} onClick={() => setTag(tag === t ? '' : t)}>{t}</button>
        ))}
      </div>

      {recentVideos.length > 0 && (
        <section style={{ marginBottom: 24 }}>
          <h3>🕘 最近观看</h3>
          <div className="videos-grid">
            {recentVideos.map(r => <VideoCard key={r.videoId} video={r.video} level={r.video.level} idx={0} />)}
          </div>
        </section>
      )}

      <div className="videos-grid">
        {videos.map(({ video }, i) => <VideoCard key={video.id} video={video} level={level} idx={i} />)}
      </div>
      {videos.length === 0 && <div className="course-empty">没有匹配的视频</div>}
    </div>
  )
}
