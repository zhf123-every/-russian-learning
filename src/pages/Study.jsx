import { useEffect, useState } from 'react'
import { useParams, useNavigate, useSearchParams } from 'react-router-dom'
import { useCourseStore } from '../store/courseStore'
import { useSquareStore } from '../store/squareStore'
import { useSessionStore } from '../store/sessionStore'
import { useShangStore, STAGES } from '../store/shangStore'
import SentenceList from '../components/SentenceList'
import SentenceBox from '../components/SentenceBox'
import StageListen from '../components/StageListen'
import StageDictate from '../components/StageDictate'
import StageRecite from '../components/StageRecite'
import { speak, speakAll, loopSentence, cancelSpeech } from '../lib/tts'
import { explainSentence } from '../lib/ai'
import { toast } from '../lib/toast'
import { mdToHtml } from '../lib/md'

// 5 个阶段提示文案（与 ShangMethod 保持一致）
const STAGE_HINTS = {
  [STAGES.LISTEN]: '阶段 1 · 整体盲听：反复听完整篇素材，俄文字幕已隐藏，目标是感受整体语境主旨。',
  [STAGES.DICTATE]: '阶段 2 · 逐句盲听听写（核心）：单句循环播放，俄文已隐藏；把听到的敲入输入框，听不出可点「跳过」。',
  [STAGES.CORRECT]: '阶段 3 · 对照精读纠错：现在显示原文。逐句对比自己的听写文本，查生词、语法、连读弱读差异。',
  [STAGES.RECITE]: '阶段 4 · 跟读模仿训练：原文已显示，单句循环，影子跟读，模仿重音、语调与语速。',
  [STAGES.RECITE_OUT]: '阶段 5 · 脱稿背诵输出（最重要）：再次隐藏全部字幕，听一句复述一句，语速尽量对齐原声。',
}
const STAGE_LABELS = {
  [STAGES.LISTEN]: '👂 阶段1 整体盲听',
  [STAGES.DICTATE]: '⌨️ 阶段2 逐句盲听听写',
  [STAGES.CORRECT]: '📖 阶段3 对照精读纠错',
  [STAGES.RECITE]: '🎤 阶段4 跟读模仿训练',
  [STAGES.RECITE_OUT]: '🧠 阶段5 脱稿背诵输出',
}

export default function Study() {
  const { videoId } = useParams()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  // 从 URL 携带 mode=shang 参数进入
  const shangMode = searchParams.get('mode') === 'shang'

  const courseVideo = useCourseStore(s => s.getVideo(videoId))
  const squareVideo = useSquareStore(s => s.getItem(videoId))
  const video = courseVideo || squareVideo
  const pushRecent = useCourseStore(s => s.pushRecent)
  const progress = useCourseStore(s => s.progress[videoId])
  const submitVideo = useCourseStore(s => s.submitVideo)
  const settings = useSettingsStoreCompat()

  const { curIdx, stage, revealed, setIdx, setStage, toggleRevealed } = useSessionStore()
  const open = useSessionStore(s => s.open)
  const shang = useShangStore()
  const shangState = shang.load(videoId) || { stage: STAGES.LISTEN, dictations: {}, reciteOk: {}, finished: false }
  const shangWenjieStage = shangState.stage
  const shangDictations = shangState.dictations || {}
  const shangReciteOk = shangState.reciteOk || {}
  const isShangFinished = !!shangState.finished

  const [playingIdx, setPlayingIdx] = useState(-1)
  const [aiHtml, setAiHtml] = useState('')
  const [showZh, setShowZh] = useState(false)
  const [shangUserInput, setShangUserInput] = useState('')
  const [shangDictResult, setShangDictResult] = useState(null)
  const [speed, setSpeed] = useState(settings?.rate || 1.0)
  const [loopMode, setLoopMode] = useState(true)

  useEffect(() => {
    if (!video) { navigate('/'); return }
    setAiHtml('')
    setShangUserInput('')
    setShangDictResult(null)
    if (shangMode) {
      // 进入尚雯婕模式：初始化进度
      shang.init(videoId)
      // 强制设置当前句到第 0 句
      useSessionStore.getState().setIdx(0)
    } else {
      open(videoId)
      pushRecent(videoId)
      const saved = progress?.lastIndex
      if (saved != null) {
        const i = video.sentences.findIndex(s => s.id === saved)
        if (i >= 0) setIdx(i)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoId, shangMode])

  // 阶段切换时重置当前句
  useEffect(() => {
    if (shangMode) {
      setShangUserInput('')
      setShangDictResult(null)
      useSessionStore.getState().setIdx(0)
      cancelSpeech()
      setPlayingIdx(-1)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shangWenjieStage])

  useEffect(() => {
    return () => { cancelSpeech() }
  }, [])

  if (!video) return null
  const sentences = (video.sentences || []).map((s, i) => ({
    ...s,
    id: s.id ?? i + 1,
    russian: s.russian ?? s.text ?? '',
    chinese: s.chinese ?? s.tr ?? '',
  }))
  const cur = sentences[curIdx]

  // 无字幕素材：仅展示视频可观看，不做逐句学习
  if (sentences.length === 0) {
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
        </div>
        <div className="col">
          <div className="card" style={{ padding: 24, textAlign: 'center' }}>
            <div style={{ fontSize: 44, marginBottom: 10 }}>📺</div>
            <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 8 }}>该视频暂无字幕</div>
            <p className="hint" style={{ margin: 0 }}>只能观看视频，暂无法逐句学习。</p>
          </div>
        </div>
      </div>
    )
  }

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

  // ========== 普通模式渲染 ==========
  const stageEl = stage === 'listen' ? <StageListen sentences={sentences} curIdx={curIdx} onSetPlaying={setPlayingIdx} />
    : stage === 'dictate' ? <StageDictate sentence={cur} onScore={(s) => useCourseStore.getState().recordSentenceScore(videoId, cur.id, { dictate: s })} />
    : <StageRecite sentence={cur} onScore={(s) => useCourseStore.getState().recordSentenceScore(videoId, cur.id, { recite: s })} />

  // ========== 尚雯婕模式：核心逻辑 ==========
  // 整体盲听：整篇连播
  const shangPlayAll = () => {
    cancelSpeech()
    setPlayingIdx(-1)
    let i = 0
    const next = () => {
      if (i >= sentences.length) { setPlayingIdx(-1); return }
      setPlayingIdx(i)
      speak(sentences[i].russian, { rate: speed, onEnd: () => { i++; next() } })
    }
    next()
  }

  // 单句 TTS（支持循环）
  const shangPlayOne = (loop = true) => {
    speak(cur.russian, {
      rate: speed,
      onStart: () => setPlayingIdx(curIdx),
      onEnd: () => {
        if (loop) shangPlayOne(true)
        else setPlayingIdx(-1)
      }
    })
  }
  const shangStop = () => { cancelSpeech(); setPlayingIdx(-1) }

  // 听写规范化
  const normDict = s => (s || '').replace(/[^\wа-яёА-ЯЁ\s]/g, '').toLowerCase().replace(/\s+/g, ' ').trim()

  const shangCheckDict = () => {
    const target = normDict(cur.russian)
    const input = normDict(shangUserInput)
    const correct = target === input
    setShangDictResult({ correct, target: cur.russian, input })
    shang.setDictation(videoId, cur.id, { text: shangUserInput, ok: correct })
  }

  const shangSkipSentence = () => {
    shang.setDictation(videoId, cur.id, { text: shangUserInput, skipped: true, ok: false })
    setShangUserInput('')
    setShangDictResult(null)
    if (curIdx < sentences.length - 1) {
      setIdx(curIdx + 1)
      setTimeout(() => speak(sentences[curIdx + 1]?.russian, { rate: speed }), 200)
    } else {
      toast('已听完所有句子，请确认完成后进入下一阶段')
    }
  }

  // 听写进度
  const dictProgress = (() => {
    const done = sentences.filter(s => {
      const d = shangDictations[s.id]
      return d && (d.ok || d.skipped)
    }).length
    return { done, total: sentences.length }
  })()

  // 跟读完成度
  const reciteProgress = (() => {
    const done = sentences.filter(s => shangReciteOk[s.id]).length
    return { done, total: sentences.length }
  })()

  const goShangStage = (target) => {
    if (target > shangWenjieStage + 1) {
      toast('请按顺序完成当前阶段，不能跳跃')
      return
    }
    if (shangWenjieStage === STAGES.DICTATE && target >= STAGES.CORRECT) {
      if (dictProgress.done < dictProgress.total) {
        toast(`听写阶段未完成（${dictProgress.done}/${dictProgress.total}）`)
        return
      }
    }
    shang.setStage(videoId, target)
  }

  const shangExit = () => {
    setSearchParams({})
  }

  const shangFinish = () => {
    shang.finish(videoId)
    toast('🎉 尚雯婕训练完成！')
  }

  // ========== 渲染 ==========
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
          {/* 顶部模式条：普通 / 尚雯婕 */}
          <div className="row" style={{ marginBottom: 10, justifyContent: 'space-between' }}>
            <div className="stages">
              {shangMode ? (
                <span className="stage active">🦜 尚雯婕学习法</span>
              ) : (
                [['listen', '👂 听'], ['dictate', '⌨️ 听写'], ['recite', '🎤 跟读']].map(([k, label]) => (
                  <span key={k} className={'stage' + (stage === k ? ' active' : '')} onClick={() => setStage(k)}>{label}</span>
                ))
              )}
            </div>
            {shangMode ? (
              <button className="btn sm" onClick={shangExit}>↩ 切回普通模式</button>
            ) : (
              <button
                className="btn sm"
                onClick={() => {
                  if (!sentences || sentences.length === 0) {
                    toast('该素材缺少分句字幕，无法使用尚雯婕学习法')
                    return
                  }
                  shang.init(videoId)
                  setSearchParams({ mode: 'shang' })
                }}
              >🦜 尚雯婕学习法</button>
            )}
          </div>

          {/* 尚雯婕模式：阶段切换 + 提示 */}
          {shangMode && (
            <>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
                {[1, 2, 3, 4, 5].map(s => (
                  <button
                    key={s}
                    className={'btn sm' + (s === shangWenjieStage ? ' primary' : '')}
                    disabled={s > shangWenjieStage + 1}
                    onClick={() => goShangStage(s)}
                    style={{ flex: '1 1 auto', minWidth: 100 }}
                  >
                    {STAGE_LABELS[s]}
                  </button>
                ))}
              </div>
              <div className="shang-hint" style={{ padding: '8px 10px', background: 'var(--soft, #F5F0E8)', border: '1px solid var(--border2, #E0D6C4)', borderRadius: 6, fontSize: 12, lineHeight: 1.55, marginBottom: 10 }}>
                {STAGE_HINTS[shangWenjieStage]}
                {isShangFinished && <span style={{ marginLeft: 8, color: '#5C8A6B', fontWeight: 600 }}>✓ 训练完成</span>}
              </div>
            </>
          )}

          {/* 句子展示：按阶段决定是否显示俄文 */}
          {shangMode ? (
            <>
              {shangWenjieStage === STAGES.LISTEN && (
                <div style={{ padding: 20, textAlign: 'center' }}>
                  <div style={{ fontSize: 50, marginBottom: 10 }}>🎧</div>
                  <div className="ru-large" style={{ opacity: 0.2 }}>俄文字幕已隐藏</div>
                  <div className="zh-medium" style={{ marginTop: 6 }}>整体盲听 · 感受语境主旨</div>
                  <div className="hint" style={{ marginTop: 8 }}>本素材共 {sentences.length} 句，请反复听完整篇</div>
                  <div style={{ marginTop: 12 }}>
                    {playingIdx === -1 ? (
                      <button className="btn primary" onClick={shangPlayAll}>▶ 整篇连播</button>
                    ) : (
                      <button className="btn" onClick={shangStop}>⏸ 停止</button>
                    )}
                  </div>
                </div>
              )}

              {shangWenjieStage === STAGES.DICTATE && (
                <>
                  <div className="ru-large" style={{ opacity: 0.2 }}>俄文字幕已隐藏</div>
                  <div className="hint" style={{ margin: '8px 0' }}>第 {curIdx + 1} 句 / 共 {sentences.length} 句 — 听写进度 {dictProgress.done}/{dictProgress.total}</div>
                  <input
                    className="qfill"
                    value={shangUserInput}
                    onChange={e => setShangUserInput(e.target.value)}
                    placeholder="在这里输入你听到的俄语..."
                  />
                  <div style={{ marginTop: 8 }}>
                    <button className="btn primary" onClick={shangCheckDict}>检查本句</button>
                    <button className="btn" onClick={() => shangPlayOne(true)} style={{ marginLeft: 8 }}>🔊 再听本句</button>
                    <button className="btn" onClick={shangSkipSentence} style={{ marginLeft: 8 }}>⏭ 跳过本句</button>
                  </div>
                  {shangDictResult && (
                    <div className={'result ' + (shangDictResult.correct ? 'ok' : 'err')} style={{ marginTop: 8 }}>
                      {shangDictResult.correct ? '✓ 完全正确！' : '✗ 有错误'}
                      {!shangDictResult.correct && (
                        <div style={{ marginTop: 4 }}>正确答案：{shangDictResult.target}</div>
                      )}
                    </div>
                  )}
                </>
              )}

              {shangWenjieStage === STAGES.CORRECT && (
                <>
                  <div className="ru-large">{cur.russian}</div>
                  {showZh && <div className="zh-medium" style={{ marginTop: 6 }}>{cur.chinese}</div>}
                  {(() => {
                    const d = shangDictations[cur.id]
                    if (!d) return null
                    return (
                      <div className="compare-box" style={{ marginTop: 10, padding: 10, background: '#FBF6EC', border: '1px solid var(--border2)', borderRadius: 6 }}>
                        <div className="hint">你刚才的听写：</div>
                        <div style={{ marginTop: 4 }}>{d.text || <span style={{ opacity: 0.5 }}>（已跳过）</span>}</div>
                        {d.skipped && <div className="hint" style={{ marginTop: 4, color: '#A86454' }}>本句为「跳过」状态，请重点精读</div>}
                      </div>
                    )
                  })()}
                  {aiHtml && <div className="translation" style={{ marginTop: 8 }} dangerouslySetInnerHTML={{ __html: aiHtml }} />}
                  <div style={{ marginTop: 8 }}>
                    <button className="btn sm" onClick={runAI}>🤖 AI 解析</button>
                    <button className="btn sm" onClick={() => setShowZh(v => !v)} style={{ marginLeft: 6 }}>{showZh ? '隐藏中译' : '显示中译'}</button>
                  </div>
                </>
              )}

              {shangWenjieStage === STAGES.RECITE && (
                <>
                  <div className="ru-large">{cur.russian}</div>
                  {showZh && <div className="zh-medium" style={{ marginTop: 6 }}>{cur.chinese}</div>}
                  <div className="mode-hint" style={{ marginTop: 10 }}>
                    <div className="hint">🎤 影子跟读：听 → 跟读 → 模仿重音、语速、语调</div>
                    <div style={{ marginTop: 8 }}>
                      <button className="btn primary" onClick={() => shangPlayOne(true)}>🔊 循环本句</button>
                      <button className="btn" onClick={() => shangPlayOne(false)} style={{ marginLeft: 6 }}>▶ 听一次</button>
                    </div>
                    <div className="row" style={{ marginTop: 10 }}>
                      <button className="btn sm" onClick={() => shang.setReciteOk(videoId, cur.id, true)}>✓ 本句跟读流畅</button>
                      <button className="btn sm" onClick={() => shang.setReciteOk(videoId, cur.id, false)}>↻ 还需要再练</button>
                    </div>
                    <div className="hint" style={{ marginTop: 6 }}>跟读完成：{reciteProgress.done}/{reciteProgress.total}</div>
                  </div>
                </>
              )}

              {shangWenjieStage === STAGES.RECITE_OUT && (
                <div style={{ padding: 16, textAlign: 'center' }}>
                  <div className="ru-large" style={{ opacity: 0.12, fontSize: 22 }}>俄文字幕已隐藏 · 脱稿复述</div>
                  <div style={{ fontSize: 45, margin: '12px 0' }}>🧠</div>
                  <div className="hint" style={{ marginBottom: 8 }}>第 {curIdx + 1} 句 / 共 {sentences.length} 句 — 复述完成 {reciteProgress.done}/{reciteProgress.total}</div>
                  <div>
                    <button className="btn primary" onClick={() => shangPlayOne(false)}>▶ 听一句</button>
                    <button className="btn" onClick={() => shangPlayOne(true)} style={{ marginLeft: 6 }}>🔁 循环一句</button>
                  </div>
                  <div className="row" style={{ marginTop: 12, justifyContent: 'center' }}>
                    <button className="btn sm" onClick={() => shang.setReciteOk(videoId, cur.id, true)}>✓ 已流利复述</button>
                    <button className="btn sm" onClick={() => shang.setReciteOk(videoId, cur.id, false)}>↻ 还需再练</button>
                  </div>
                  {isShangFinished && <div style={{ marginTop: 14, color: '#5C8A6B', fontWeight: 600 }}>🎉 本素材尚雯婕训练已完成</div>}
                </div>
              )}

              {/* 通用控件：变速、循环、播放、导航 */}
              <div className="ctrl-row" style={{ marginTop: 12, display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                <button className="btn sm" onClick={() => go(-1)} disabled={curIdx === 0}>← 上一句</button>
                <button className="btn sm primary" onClick={() => shangPlayOne(loopMode)}>▶ 播放本句</button>
                <button className={'btn sm' + (loopMode ? ' primary' : '')} onClick={() => setLoopMode(v => !v)}>🔁 循环</button>
                <select className="speed-select" value={speed} onChange={e => setSpeed(parseFloat(e.target.value))}>
                  <option value={0.5}>0.5x</option>
                  <option value={0.75}>0.75x</option>
                  <option value={1.0}>1.0x</option>
                  <option value={1.25}>1.25x</option>
                  <option value={1.5}>1.5x</option>
                </select>
                <span className="pos">{curIdx + 1} / {sentences.length}</span>
                <button className="btn sm" onClick={() => go(1)} disabled={curIdx === sentences.length - 1}>下一句 →</button>
              </div>

              {/* 阶段切换：上一阶段 / 下一阶段 */}
              <div className="ctrl-row" style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {shangWenjieStage > STAGES.LISTEN && (
                  <button className="btn sm" onClick={() => goShangStage(shangWenjieStage - 1)}>← 上一阶段</button>
                )}
                {shangWenjieStage < STAGES.RECITE_OUT && (
                  <button
                    className="btn sm primary"
                    onClick={() => goShangStage(shangWenjieStage + 1)}
                  >
                    {shangWenjieStage === STAGES.DICTATE && dictProgress.done < dictProgress.total
                      ? `下一阶段（先完成 ${dictProgress.done}/${dictProgress.total}）`
                      : '进入下一阶段 →'}
                  </button>
                )}
                {shangWenjieStage === STAGES.RECITE_OUT && reciteProgress.done >= reciteProgress.total && !isShangFinished && (
                  <button className="btn sm primary" onClick={shangFinish}>🎉 完成尚雯婕训练</button>
                )}
              </div>
            </>
          ) : (
            <>
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
            </>
          )}
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

// 兼容 settings store 的小工具（settings 可能为空）
function useSettingsStoreCompat() {
  try {
    const { useSettingsStore } = require('../store/settingsStore')
    return useSettingsStore()
  } catch (e) {
    return { settings: { rate: 1.0 } }
  }
}
