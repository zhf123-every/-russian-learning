import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useVocabStore } from '../store/vocabStore'
import { useShangStore, STAGES } from '../store/shangStore'
import { explainSentence } from '../lib/ai'
import { toast } from '../lib/toast'
import { courseLibrary, LEVELS } from '../data/courseLibrary'

const LEVEL_COLORS = { A1: '#8B735F', A2: '#A8937F', B1: '#B08A5A', B2: '#A86454' }

// 5 个阶段的提示文案（还原原版尚雯婕学习法核心理念）
const STAGE_HINTS = {
  [STAGES.LISTEN]: '阶段 1 · 整体盲听：闭眼或看着封面，反复听完整篇素材。字幕已强制隐藏，目标是感受整体语境、节奏与主旨，不看文字。',
  [STAGES.DICTATE]: '阶段 2 · 逐句盲听听写（核心）：单句循环播放，俄文已隐藏。把你听到的句子敲进输入框；实在听不出可点「跳过本句」。',
  [STAGES.CORRECT]: '阶段 3 · 对照精读纠错：现在才显示原文。逐句对比自己的听写文本，查生词、语法、连读弱读差异，全部吃透后再进入下一阶段。',
  [STAGES.RECITE]: '阶段 4 · 跟读模仿训练：原文已显示，单句循环播放，影子跟读，模仿重音、语调与语速；可录音对比原声。',
  [STAGES.RECITE_OUT]: '阶段 5 · 脱稿背诵输出（最重要）：再次隐藏全部字幕，听一句复述一句。尽量贴合原声音频的语速与节奏，完整复述整篇即训练完成。',
}

const STAGE_LABELS = {
  [STAGES.LISTEN]: '👂 阶段1 整体盲听',
  [STAGES.DICTATE]: '⌨️ 阶段2 逐句盲听听写',
  [STAGES.CORRECT]: '📖 阶段3 对照精读纠错',
  [STAGES.RECITE]: '🎤 阶段4 跟读模仿训练',
  [STAGES.RECITE_OUT]: '🧠 阶段5 脱稿背诵输出',
}

export default function ShangMethod() {
  const { level } = useParams()
  const navigate = useNavigate()
  const addWord = useVocabStore(s => s.addWord)

  const [selectedLevel, setSelectedLevel] = useState(level || 'A1')
  const [selectedCollection, setSelectedCollection] = useState(null)
  const [curIdx, setCurIdx] = useState(0)
  const [speed, setSpeed] = useState(1.0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [loopMode, setLoopMode] = useState(true)
  const [userInput, setUserInput] = useState('')
  const [dictationResult, setDictationResult] = useState(null)
  const [grammar, setGrammar] = useState(null)
  const [grammarLoading, setGrammarLoading] = useState(false)
  const [marks, setMarks] = useState(() => {
    try { return JSON.parse(localStorage.getItem('shang_marks_' + (level || 'A1')) || '{}') } catch { return {} }
  })

  const shang = useShangStore()
  // 阶段 1..5，沿用 shangWenjieStage 字段
  const [shangWenjieStage, setShangWenjieStage] = useState(STAGES.LISTEN)

  const courseData = courseLibrary[selectedLevel]
  const collections = courseData?.collections || []
  const currentCollection = selectedCollection !== null ? collections[selectedCollection] : null
  const sentences = currentCollection?.videos?.[0]?.sentences || []
  const currentSentence = sentences[curIdx]
  // 给每条句子分配稳定 id（用于 shang 进度存储）
  const sentencesWithId = sentences.map((s, i) => ({ ...s, id: s.id ?? i + 1 }))
  const currentSentenceWithId = sentencesWithId[curIdx]
  const materialId = currentCollection ? `shang_${selectedLevel}_${currentCollection.id}` : null

  useEffect(() => {
    localStorage.setItem('shang_marks_' + selectedLevel, JSON.stringify(marks))
  }, [marks, selectedLevel])

  // 切换素材时：初始化尚雯婕阶段进度
  useEffect(() => {
    if (!materialId) return
    shang.init(materialId)
    const p = shang.load(materialId)
    if (p && p.stage) setShangWenjieStage(p.stage)
    setCurIdx(0)
    setUserInput('')
    setDictationResult(null)
    setGrammar(null)
    if (window.speechSynthesis) window.speechSynthesis.cancel()
    setIsPlaying(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [materialId])

  useEffect(() => {
    return () => { if (window.speechSynthesis) window.speechSynthesis.cancel() }
  }, [])

  // TTS 播放（支持变速 + 循环）
  const playTTS = (text, loopOnce = false) => {
    if (!text) return
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel()
      const utter = new SpeechSynthesisUtterance(text)
      utter.lang = 'ru-RU'
      utter.rate = speed
      utter.onend = () => {
        setIsPlaying(false)
        if (loopMode || loopOnce) playTTS(text, loopOnce)
      }
      window.speechSynthesis.speak(utter)
      setIsPlaying(true)
    }
  }

  // 阶段 1：整篇连播
  const playAll = () => {
    if (sentencesWithId.length === 0) return
    if (window.speechSynthesis) window.speechSynthesis.cancel()
    setIsPlaying(true)
    let i = 0
    const next = () => {
      if (i >= sentencesWithId.length) { setIsPlaying(false); return }
      const s = sentencesWithId[i]
      const utter = new SpeechSynthesisUtterance(s.russian)
      utter.lang = 'ru-RU'
      utter.rate = speed
      utter.onend = () => { i++; next() }
      window.speechSynthesis.speak(utter)
    }
    next()
  }

  const stopPlay = () => {
    if (window.speechSynthesis) window.speechSynthesis.cancel()
    setIsPlaying(false)
  }

  const pickCollection = (i) => {
    setSelectedCollection(i)
  }

  const goPrev = () => {
    if (curIdx > 0) {
      setUserInput('')
      setDictationResult(null)
      setCurIdx(curIdx - 1)
    }
  }
  const goNext = () => {
    if (curIdx < sentences.length - 1) {
      setUserInput('')
      setDictationResult(null)
      setCurIdx(curIdx + 1)
    }
  }

  // 阶段推进
  const goStage = (target) => {
    // 顺序不可逆：可回退上一阶段，不可跳跃
    if (target > shangWenjieStage + 1) {
      toast('请按顺序完成当前阶段，不能跳跃')
      return
    }
    // 阶段 2 听写未全部完成，不允许进入阶段 3
    if (shangWenjieStage === STAGES.DICTATE && target >= STAGES.CORRECT) {
      const total = sentencesWithId.length
      const done = sentencesWithId.filter(s => {
        const d = shang.load(materialId)?.dictations?.[s.id]
        return d && (d.ok || d.skipped)
      }).length
      if (done < total) {
        toast(`听写阶段未完成（${done}/${total}），请先完成所有句子`)
        return
      }
    }
    setShangWenjieStage(target)
    if (materialId) shang.setStage(materialId, target)
    setCurIdx(0)
    setUserInput('')
    setDictationResult(null)
    if (window.speechSynthesis) window.speechSynthesis.cancel()
    setIsPlaying(false)
  }

  // 阶段 2：检查听写
  const norm = s => (s || '').replace(/[^\wа-яёА-ЯЁ\s]/g, '').toLowerCase().replace(/\s+/g, ' ').trim()

  const checkDictation = () => {
    if (!currentSentenceWithId) return
    const target = norm(currentSentenceWithId.russian)
    const input = norm(userInput)
    const correct = target === input
    setDictationResult({ correct, target: currentSentenceWithId.russian, input })
    if (materialId) {
      shang.setDictation(materialId, currentSentenceWithId.id, { text: userInput, ok: correct })
    }
  }

  // 阶段 2：跳过本句
  const skipSentence = () => {
    if (!currentSentenceWithId || !materialId) return
    shang.setDictation(materialId, currentSentenceWithId.id, { text: userInput, skipped: true, ok: false })
    setUserInput('')
    setDictationResult(null)
    if (curIdx < sentencesWithId.length - 1) {
      setCurIdx(curIdx + 1)
      // 自动播放下一句
      setTimeout(() => playTTS(sentencesWithId[curIdx + 1]?.russian, true), 200)
    } else {
      toast('已听完所有句子，请确认完成后进入下一阶段')
    }
  }

  // 阶段 2：当前听写是否完成全部句子
  const dictationProgress = (() => {
    if (!materialId) return { done: 0, total: 0 }
    const dictations = shang.load(materialId)?.dictations || {}
    const done = sentencesWithId.filter(s => {
      const d = dictations[s.id]
      return d && (d.ok || d.skipped)
    }).length
    return { done, total: sentencesWithId.length }
  })()

  // 阶段 4：跟读自评
  const markRecite = (ok) => {
    if (!currentSentenceWithId || !materialId) return
    shang.setReciteOk(materialId, currentSentenceWithId.id, ok)
  }

  // 阶段 4 全部跟读通过
  const reciteProgress = (() => {
    if (!materialId) return { done: 0, total: 0 }
    const ok = shang.load(materialId)?.reciteOk || {}
    const done = sentencesWithId.filter(s => ok[s.id]).length
    return { done, total: sentencesWithId.length }
  })()

  // 阶段 5：标记本句复述完成（流利度自评）
  const markReciteOut = (ok) => {
    if (!currentSentenceWithId || !materialId) return
    shang.setReciteOk(materialId, currentSentenceWithId.id, ok)
  }

  // 阶段 5 全部复述通过 → 完成训练
  const finishShang = () => {
    if (!materialId) return
    shang.finish(materialId)
    toast('🎉 尚雯婕训练完成！')
    setShangWenjieStage(STAGES.RECITE_OUT)
  }

  // 语法解释（任何阶段都可触发，用于阶段 3 精读）
  const explainGrammar = async () => {
    if (!currentSentenceWithId) return
    setGrammarLoading(true)
    setGrammar(null)
    try {
      const res = await explainSentence(currentSentenceWithId.russian)
      setGrammar(res)
    } catch (e) {
      toast('AI 解析失败：' + e.message)
    } finally {
      setGrammarLoading(false)
    }
  }

  const markSentence = (mark) => {
    setMarks(prev => ({ ...prev, [curIdx]: mark }))
  }

  // 主题选择页
  if (selectedCollection === null) {
    return (
      <div className="course">
        <div className="row" style={{ marginBottom: 16 }}>
          <button className="btn sm" onClick={() => navigate('/course')}>← 返回分级课程</button>
        </div>
        <h2>尚雯婕学习法</h2>
        <p className="hint">纯听觉 + 文字专注训练，每个级别包含多个主题。完整流程：整体盲听 → 逐句盲听听写 → 对照精读纠错 → 跟读模仿 → 脱稿背诵输出。</p>

        <div className="course-levels">
          {LEVELS.map(l => (
            <button
              key={l}
              className={'btn' + (l === selectedLevel ? ' primary' : '')}
              onClick={() => setSelectedLevel(l)}
            >
              {l}
            </button>
          ))}
        </div>

        <div className="videos-grid">
          {collections.map((col, i) => {
            const mid = `shang_${selectedLevel}_${col.id}`
            const finished = shang.isFinished(mid)
            return (
              <div key={col.id} className="card" onClick={() => pickCollection(i)} style={{ cursor: 'pointer' }}>
                <div className="vc-body">
                  <div className="vc-title">{col.name} {finished && <span className="chip" style={{ marginLeft: 6 }}>✓ 训练完成</span>}</div>
                  <div className="vc-meta">{col.videos?.[0]?.sentences?.length || 0} 句</div>
                  <div className="vc-meta">{col.description}</div>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  if (!currentSentence) {
    return (
      <div className="course">
        <div className="empty">没有可学习的内容</div>
        <button className="btn" onClick={() => setSelectedCollection(null)}>返回</button>
      </div>
    )
  }

  const isFinished = shang.isFinished(materialId)

  // ========== 渲染主区 ==========
  return (
    <div className="method-wrap">
      <div className="method-header">
        <button className="btn sm" onClick={() => setSelectedCollection(null)}>← 返回</button>
        <span className="level-badge" style={{ background: LEVEL_COLORS[selectedLevel] || 'var(--accent)' }}>{selectedLevel}</span>
        <span className="theme-name">{currentCollection?.name}</span>
        <span className="progress">{curIdx + 1} / {sentences.length}</span>
        {isFinished && <span className="chip" style={{ background: '#5C8A6B', color: '#fff' }}>✓ 尚雯婕训练完成</span>}
      </div>

      {/* 阶段切换条（1→5 顺序不可逆，可回退上一阶段） */}
      <div className="shang-stages" style={{ display: 'flex', gap: 6, flexWrap: 'wrap', margin: '10px 0 14px' }}>
        {[1, 2, 3, 4, 5].map(s => (
          <button
            key={s}
            className={'btn sm' + (s === shangWenjieStage ? ' primary' : '')}
            disabled={s > shangWenjieStage + 1}
            onClick={() => goStage(s)}
            style={{ flex: '1 1 auto', minWidth: 110 }}
          >
            {STAGE_LABELS[s]}
          </button>
        ))}
      </div>

      {/* 当前阶段提示文案（核心方法论） */}
      <div className="shang-hint" style={{ padding: '10px 12px', background: 'var(--soft, #F5F0E8)', border: '1px solid var(--border2, #E0D6C4)', borderRadius: 8, marginBottom: 12, fontSize: 13, lineHeight: 1.6 }}>
        {STAGE_HINTS[shangWenjieStage]}
      </div>

      {/* 上半区：句子 + 释义（按阶段决定是否显示俄文） */}
      <div className="method-sentence">
        {shangWenjieStage === STAGES.LISTEN && (
          <div className="blind-box" style={{ padding: 30, textAlign: 'center' }}>
            <div style={{ fontSize: 60, marginBottom: 12 }}>🎧</div>
            <div className="ru-large" style={{ opacity: 0.25 }}>俄文字幕已隐藏</div>
            <div className="zh-medium" style={{ marginTop: 8 }}>整体盲听 · 感受语境主旨</div>
            <div className="hint" style={{ marginTop: 12 }}>本素材共 {sentencesWithId.length} 句，请反复听完整篇</div>
            <div style={{ marginTop: 16 }}>
              {!isPlaying ? (
                <button className="btn primary" onClick={playAll}>▶ 整篇连播</button>
              ) : (
                <button className="btn" onClick={stopPlay}>⏸ 停止播放</button>
              )}
            </div>
          </div>
        )}

        {shangWenjieStage === STAGES.DICTATE && (
          <>
            <div className="ru-large" style={{ opacity: 0.25 }}>俄文字幕已隐藏</div>
            <div className="dictate-box" style={{ marginTop: 12 }}>
              <div className="hint" style={{ marginBottom: 6 }}>第 {curIdx + 1} 句 / 共 {sentencesWithId.length} 句 — 听写进度 {dictationProgress.done}/{dictationProgress.total}</div>
              <input
                className="qfill"
                value={userInput}
                onChange={e => setUserInput(e.target.value)}
                placeholder="在这里输入你听到的俄语..."
              />
              <div style={{ marginTop: 8 }}>
                <button className="btn primary" onClick={checkDictation}>检查本句</button>
                <button className="btn" onClick={() => playTTS(currentSentenceWithId.russian, true)} style={{ marginLeft: 8 }}>🔊 再听本句</button>
                <button className="btn" onClick={skipSentence} style={{ marginLeft: 8 }}>⏭ 跳过本句</button>
              </div>
              {dictationResult && (
                <div className={'result ' + (dictationResult.correct ? 'ok' : 'err')} style={{ marginTop: 8 }}>
                  {dictationResult.correct ? '✓ 完全正确！' : '✗ 有错误'}
                  {!dictationResult.correct && (
                    <div style={{ marginTop: 4 }}>正确答案：{dictationResult.target}</div>
                  )}
                </div>
              )}
            </div>
          </>
        )}

        {shangWenjieStage === STAGES.CORRECT && (
          <>
            <div className="ru-large">{currentSentenceWithId.russian}</div>
            <div className="zh-medium">{currentSentenceWithId.chinese}</div>
            {(() => {
              const d = shang.load(materialId)?.dictations?.[currentSentenceWithId.id]
              if (!d) return null
              return (
                <div className="compare-box" style={{ marginTop: 10, padding: 10, background: '#FBF6EC', border: '1px solid var(--border2)', borderRadius: 6 }}>
                  <div className="hint">你刚才的听写：</div>
                  <div style={{ marginTop: 4 }}>{d.text || <span style={{ opacity: 0.5 }}>（已跳过）</span>}</div>
                  {d.skipped && <div className="hint" style={{ marginTop: 4, color: '#A86454' }}>本句为「跳过」状态，请重点精读</div>}
                </div>
              )
            })()}
            <div className="grammar-box" style={{ marginTop: 10 }}>
              {grammarLoading ? (
                <div className="hint">AI 解析中...</div>
              ) : grammar ? (
                <div className="ai-out" dangerouslySetInnerHTML={{ __html: grammar.replace(/\n/g, '<br/>') }} />
              ) : (
                <button className="btn sm" onClick={explainGrammar}>🤖 AI 单词/语法解析</button>
              )}
            </div>
          </>
        )}

        {shangWenjieStage === STAGES.RECITE && (
          <>
            <div className="ru-large">{currentSentenceWithId.russian}</div>
            <div className="zh-medium">{currentSentenceWithId.chinese}</div>
            <div className="mode-hint" style={{ marginTop: 10 }}>
              <div className="hint">🎤 影子跟读：听 → 跟读 → 模仿重音、语速、语调</div>
              <div style={{ marginTop: 8 }}>
                <button className="btn primary" onClick={() => playTTS(currentSentenceWithId.russian, true)}>🔊 循环本句</button>
                <button className="btn" onClick={() => playTTS(currentSentenceWithId.russian)} style={{ marginLeft: 8 }}>▶ 听一次</button>
              </div>
              <div className="row" style={{ marginTop: 10 }}>
                <button className="btn sm" onClick={() => markRecite(true)}>✓ 本句跟读流畅</button>
                <button className="btn sm" onClick={() => markRecite(false)}>↻ 还需要再练</button>
              </div>
              <div className="hint" style={{ marginTop: 6 }}>跟读完成：{reciteProgress.done}/{reciteProgress.total}</div>
            </div>
          </>
        )}

        {shangWenjieStage === STAGES.RECITE_OUT && (
          <div className="recite-out-box" style={{ padding: 20, textAlign: 'center' }}>
            <div className="ru-large" style={{ opacity: 0.15, fontSize: 22 }}>俄文字幕已隐藏 · 脱稿复述</div>
            <div style={{ fontSize: 50, margin: '14px 0' }}>🧠</div>
            <div className="hint" style={{ marginBottom: 10 }}>第 {curIdx + 1} 句 / 共 {sentencesWithId.length} 句 — 复述完成 {reciteProgress.done}/{reciteProgress.total}</div>
            <div>
              <button className="btn primary" onClick={() => playTTS(currentSentenceWithId.russian, false)}>▶ 听一句</button>
              <button className="btn" onClick={() => playTTS(currentSentenceWithId.russian, true)} style={{ marginLeft: 8 }}>🔁 循环一句</button>
            </div>
            <div className="row" style={{ marginTop: 14, justifyContent: 'center' }}>
              <button className="btn sm" onClick={() => markReciteOut(true)}>✓ 已流利复述</button>
              <button className="btn sm" onClick={() => markReciteOut(false)}>↻ 还需再练</button>
            </div>
            {isFinished && (
              <div style={{ marginTop: 16, color: '#5C8A6B', fontWeight: 600 }}>🎉 本素材尚雯婕训练已完成</div>
            )}
          </div>
        )}
      </div>

      {/* 下半区：通用操作（变速、循环、上一句/下一句、阶段切换） */}
      <div className="method-controls">
        <div className="ctrl-row">
          <button className="btn" onClick={goPrev} disabled={curIdx === 0}>← 上一句</button>
          <button className="btn primary" onClick={() => playTTS(currentSentenceWithId.russian)}>
            {isPlaying ? '⏸ 播放中' : '▶ 播放'}
          </button>
          <button className={'btn' + (loopMode ? ' primary' : '')} onClick={() => setLoopMode(!loopMode)}>
            🔁 循环播放
          </button>
          <select className="speed-select" value={speed} onChange={e => setSpeed(parseFloat(e.target.value))}>
            <option value={0.5}>0.5x</option>
            <option value={0.75}>0.75x</option>
            <option value={1.0}>1.0x</option>
            <option value={1.25}>1.25x</option>
            <option value={1.5}>1.5x</option>
          </select>
          <button className="btn" onClick={goNext} disabled={curIdx === sentences.length - 1}>下一句 →</button>
        </div>

        {/* 阶段切换按钮 */}
        <div className="ctrl-row">
          {shangWenjieStage > STAGES.LISTEN && (
            <button className="btn sm" onClick={() => goStage(shangWenjieStage - 1)}>← 上一阶段</button>
          )}
          {shangWenjieStage < STAGES.RECITE_OUT && (
            <button className="btn sm primary" onClick={() => goStage(shangWenjieStage + 1)}>
              {shangWenjieStage === STAGES.DICTATE && dictationProgress.done < dictationProgress.total
                ? `下一阶段（先完成 ${dictationProgress.done}/${dictationProgress.total}）`
                : '进入下一阶段 →'}
            </button>
          )}
          {shangWenjieStage === STAGES.RECITE_OUT && reciteProgress.done >= reciteProgress.total && !isFinished && (
            <button className="btn sm primary" onClick={finishShang}>🎉 完成尚雯婕训练</button>
          )}
        </div>

        <div className="ctrl-row mark-row">
          <button className="btn sm" onClick={() => addWord({ word: currentSentenceWithId.russian, chinese: currentSentenceWithId.chinese, source: 'shang' })}>＋ 生词</button>
          <button className={'btn sm' + (marks[curIdx] === 'mastered' ? ' primary' : '')} onClick={() => markSentence('mastered')}>✓ 掌握</button>
          <button className={'btn sm' + (marks[curIdx] === 'weak' ? ' danger' : '')} onClick={() => markSentence('weak')}>⚠ 薄弱</button>
        </div>
      </div>
    </div>
  )
}
