import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useCourseStore } from '../store/courseStore'
import { useSquareStore } from '../store/squareStore'
import { useSessionStore } from '../store/sessionStore'
import SentenceList from '../components/SentenceList'
import SentenceBox from '../components/SentenceBox'
import StageListen from '../components/StageListen'
import StageDictate from '../components/StageDictate'
import StageRecite from '../components/StageRecite'
import { explainSentence } from '../lib/ai'
import { toast } from '../lib/toast'
import { mdToHtml } from '../lib/md'

export default function Study() {
  const { videoId } = useParams()
  const navigate = useNavigate()
  const courseVideo = useCourseStore(s => s.getVideo(videoId))
  const squareVideo = useSquareStore(s => s.getItem(videoId))
  const video = courseVideo || squareVideo
  const pushRecent = useCourseStore(s => s.pushRecent)
  const progress = useCourseStore(s => s.progress[videoId])
  const submitVideo = useCourseStore(s => s.submitVideo)

  const { curIdx, stage, revealed, setIdx, setStage, toggleRevealed } = useSessionStore()
  const open = useSessionStore(s => s.open)

  const [playingIdx, setPlayingIdx] = useState(-1)
  const [aiHtml, setAiHtml] = useState('')
  const [showZh, setShowZh] = useState(false)

  useEffect(() => {
    if (!video) { navigate('/'); return }
    setAiHtml('')
    open(videoId)
    pushRecent(videoId)
    const saved = progress?.lastIndex
    if (saved != null) {
      const i = video.sentences.findIndex(s => s.id === saved)
      if (i >= 0) setIdx(i)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoId])

  if (!video) return null
  const sentences = (video.sentences || []).map((s, i) => ({
    ...s,
    id: s.id ?? i + 1,
    russian: s.russian ?? s.text ?? '',
    chinese: s.chinese ?? s.tr ?? '',
  }))
  const cur = sentences[curIdx]

  const go = (d) => {
    setAiHtml('')
    const n = curIdx + d
    if (n < 0 || n >= sentences.length) return
    setIdx(n)
  }

  const runAI = async () => {
    setAiHtml('解析中…')
    try { setAiHtml(mdToHtml(await explainSentence(cur.russian))) }
    catch (e) { setAiHtml(''); toast(e.message) }
  }

  const stageEl = stage === 'listen' ? <StageListen sentences={sentences} curIdx={curIdx} onSetPlaying={setPlayingIdx} />
    : stage === 'dictate' ? <StageDictate sentence={cur} onScore={(s) => useCourseStore.getState().recordSentenceScore(videoId, cur.id, { dictate: s })} />
    : <StageRecite sentence={cur} onScore={(s) => useCourseStore.getState().recordSentenceScore(videoId, cur.id, { recite: s })} />

  return (
    <div className="main">
      <div className="col">
        <div className="card" style={{ padding: 10 }}>
          <div className="video-wrap">
            {video.videoUrl ? (
              <video
                src={`/api/stream?url=${encodeURIComponent(video.videoUrl)}`}
                poster={video.posterUrl || video.thumbnail}
                controls
                playsInline
              />
            ) : (
              <img src={video.posterUrl || video.thumbnail} alt="" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
            )}
          </div>
        </div>
        <div className="card">
          <div style={{ fontWeight: 600, marginBottom: 6 }}>台词列表 <span style={{ color: 'var(--muted)', fontWeight: 400, fontSize: 13 }}>{sentences.length} 句</span></div>
          <SentenceList sentences={sentences} curIdx={curIdx} playingIdx={playingIdx} onPick={setIdx} />
        </div>
      </div>

      <div className="col">
        <div className="card">
          <div className="stages">
            {[['listen', '👂 听'], ['dictate', '⌨️ 听写'], ['recite', '🎤 跟读']].map(([k, label]) => (
              <div key={k} className={'stage' + (stage === k ? ' active' : '')} onClick={() => setStage(k)}>{label}</div>
            ))}
          </div>

          <div style={{ marginTop: 12 }}><SentenceBox sentence={cur} revealed={revealed} /></div>
          {showZh && <div className="translation"><div className="zh-label">中文翻译</div><div>{cur.chinese}</div></div>}
          {aiHtml && <div className="translation" dangerouslySetInnerHTML={{ __html: aiHtml }} />}

          <div style={{ marginTop: 12 }}>{stageEl}</div>

          <div className="row" style={{ marginTop: 14 }}>
            <button className="btn sm" onClick={toggleRevealed}>{revealed ? '隐藏原文' : '显示原文'}</button>
            <button className="btn sm" onClick={() => setShowZh(v => !v)}>{showZh ? '隐藏中译' : '中译'}</button>
            <button className="btn sm" onClick={runAI}>🤖 AI 解析</button>
          </div>

          <div className="nav-arrows">
            <button className="btn sm" onClick={() => go(-1)}>← 上一句</button>
            <span className="pos">{curIdx + 1} / {sentences.length}</span>
            <button className="btn sm" onClick={() => go(1)}>下一句 →</button>
          </div>
        </div>
      </div>

      <div className="card" style={{ gridColumn: '1/-1' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600 }}>📚 课程视频</div>
            <div className="hint" style={{ margin: 0 }}>完成听写/跟读后提交评测计算得分</div>
          </div>
          <button className="btn primary" onClick={() => { const s = submitVideo(videoId); navigate('/') }}>✅ 提交评测</button>
        </div>
      </div>
    </div>
  )
}
