import { Link } from 'react-router-dom'
import { useCourseStore } from '../store/courseStore'

export default function VideoCard({ video, level, idx }) {
  const progress = useCourseStore(s => s.progress[video.id])
  const unlocked = useCourseStore(s => s.isVideoUnlocked(level, idx))
  const pct = progress?.done ? progress.score : null

  const body = (
    <div className="video-card">
      <div className="thumb" style={{ backgroundImage: `url(${video.thumbnail || 'https://picsum.photos/seed/placeholder/400/280'})` }}>
        {pct != null && <span className="thumb-score">{pct}分</span>}
        {!unlocked && <span className="thumb-lock">🔒</span>}
      </div>
      <div className="vc-body">
        <div className="vc-title">{video.title}</div>
        <div className="vc-meta">
          <span>{video.level || '自定义'}</span> · <span>{video.duration || '—'}</span> · <span>{video.words ?? 0} 词</span>
        </div>
        <div className="vc-tags">{(video.tags || []).map(t => <span key={t} className="chip">{t}</span>)}</div>
      </div>
    </div>
  )

  if (!unlocked) return <div className="vc-locked">{body}</div>
  return <Link to={`/study/${video.id}`} className="vc-link">{body}</Link>
}
