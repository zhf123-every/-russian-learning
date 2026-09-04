import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useVocabStore } from '../store/vocabStore'
import { explainSentence } from '../lib/ai'
import { toast } from '../lib/toast'
import { courseLibrary, LEVELS } from '../data/courseLibrary'

const LEVEL_COLORS = { A1: '#2C6E5F', A2: '#5B7DB1', B1: '#B45309', B2: '#B42318' }

export default function ShangMethod() {
  const { level } = useParams()
  const navigate = useNavigate()
  const addWord = useVocabStore(s => s.addWord)

  const [selectedLevel, setSelectedLevel] = useState(level || 'A1')
  const [selectedCollection, setSelectedCollection] = useState(null)
  const [curIdx, setCurIdx] = useState(0)
  const [mode, setMode] = useState('normal') // normal | recite | dictate | memorize | grammar
  const [speed, setSpeed] = useState(1.0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [loopMode, setLoopMode] = useState(false)
  const [showZh, setShowZh] = useState(true)
  const [userInput, setUserInput] = useState('')
  const [dictationResult, setDictationResult] = useState(null)
  const [grammar, setGrammar] = useState(null)
  const [grammarLoading, setGrammarLoading] = useState(false)
  const [memorizeRevealed, setMemorizeRevealed] = useState(false)
  const [marks, setMarks] = useState(() => {
    try { return JSON.parse(localStorage.getItem('shang_marks_' + (level || 'A1')) || '{}') } catch { return {} }
  })

  const courseData = courseLibrary[selectedLevel]
  const collections = courseData?.collections || []
  const currentCollection = selectedCollection !== null ? collections[selectedCollection] : null
  const sentences = currentCollection?.videos?.[0]?.sentences || []
  const currentSentence = sentences[curIdx]

  useEffect(() => {
    localStorage.setItem('shang_marks_' + selectedLevel, JSON.stringify(marks))
  }, [marks, selectedLevel])

  useEffect(() => {
    return () => { if (window.speechSynthesis) window.speechSynthesis.cancel() }
  }, [])

  // TTS 播放（支持变速 + 循环）
  const playTTS = (text) => {
    if (!text) return
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel()
      const utter = new SpeechSynthesisUtterance(text)
      utter.lang = 'ru-RU'
      utter.rate = speed
      utter.onend = () => {
        setIsPlaying(false)
        if (loopMode) playTTS(text)
      }
      window.speechSynthesis.speak(utter)
      setIsPlaying(true)
    }
  }

  const pickCollection = (i) => {
    setSelectedCollection(i)
    setCurIdx(0)
    setMode('normal')
    setUserInput('')
    setDictationResult(null)
    setGrammar(null)
    setMemorizeRevealed(false)
  }

  const goPrev = () => { if (curIdx > 0) { resetMode(); setCurIdx(curIdx - 1) } }
  const goNext = () => { if (curIdx < sentences.length - 1) { resetMode(); setCurIdx(curIdx + 1) } }

  const resetMode = () => {
    setMode('normal')
    setUserInput('')
    setDictationResult(null)
    setGrammar(null)
    setMemorizeRevealed(false)
    if (window.speechSynthesis) window.speechSynthesis.cancel()
    setIsPlaying(false)
  }

  // 跟读模式
  const startRecite = () => {
    if (!currentSentence) return
    setMode('recite')
    playTTS(currentSentence.russian)
  }

  // 听写模式
  const startDictate = () => {
    if (!currentSentence) return
    setMode('dictate')
    setUserInput('')
    setDictationResult(null)
    playTTS(currentSentence.russian)
  }

  const checkDictation = () => {
    if (!currentSentence) return
    const norm = s => (s || '').replace(/[^\wа-яёА-ЯЁ\s]/g, '').toLowerCase().replace(/\s+/g, ' ').trim()
    const target = norm(currentSentence.russian)
    const input = norm(userInput)
    const correct = target === input
    setDictationResult({ correct, target: currentSentence.russian, input })
  }

  // 逐句背诵模式
  const startMemorize = () => {
    setMode('memorize')
    setMemorizeRevealed(false)
    if (window.speechSynthesis) window.speechSynthesis.cancel()
  }

  // 语法解释
  const explainGrammar = async () => {
    if (!currentSentence) return
    setMode('grammar')
    setGrammarLoading(true)
    setGrammar(null)
    try {
      const res = await explainSentence(currentSentence.russian)
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
        <p className="hint">纯听觉 + 文字专注训练，每个级别包含多个主题</p>

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
          {collections.map((col, i) => (
            <div key={col.id} className="card" onClick={() => pickCollection(i)} style={{ cursor: 'pointer' }}>
              <div className="vc-body">
                <div className="vc-title">{col.name}</div>
                <div className="vc-meta">{col.videos?.[0]?.sentences?.length || 0} 句</div>
                <div className="vc-meta">{col.description}</div>
              </div>
            </div>
          ))}
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

  return (
    <div className="method-wrap">
      <div className="method-header">
        <button className="btn sm" onClick={() => setSelectedCollection(null)}>← 返回</button>
        <span className="level-badge" style={{ background: LEVEL_COLORS[selectedLevel] || 'var(--accent)' }}>{selectedLevel}</span>
        <span className="theme-name">{currentCollection?.name}</span>
        <span className="progress">{curIdx + 1} / {sentences.length}</span>
      </div>

      {/* 上半区：句子 + 释义 */}
      <div className="method-sentence">
        {mode === 'memorize' ? (
          <div className="memorize-box">
            {memorizeRevealed ? (
              <>
                <div className="ru-large">{currentSentence.russian}</div>
                <div className="zh-medium">{currentSentence.chinese}</div>
              </>
            ) : (
              <div className="hint">📝 先在心里背诵这句话，再点「显示」对照</div>
            )}
            <div style={{ marginTop: 12 }}>
              <button className="btn sm" onClick={() => setMemorizeRevealed(v => !v)}>
                {memorizeRevealed ? '🙈 隐藏' : '👁 显示'}
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="ru-large">{mode === 'dictate' ? '＿＿＿' : currentSentence.russian}</div>
            {showZh && mode !== 'dictate' && (
              <div className="zh-medium">{currentSentence.chinese}</div>
            )}
          </>
        )}

        {mode === 'recite' && (
          <div className="mode-hint">
            <div className="hint">🎤 跟读模式：先听原音，再大声模仿</div>
            <button className="btn sm" style={{ marginTop: 8 }} onClick={() => playTTS(currentSentence.russian)}>🔊 再听一次</button>
          </div>
        )}

        {mode === 'dictate' && (
          <div className="dictate-box">
            <input
              className="qfill"
              value={userInput}
              onChange={e => setUserInput(e.target.value)}
              placeholder="在这里输入你听到的俄语..."
            />
            <div style={{ marginTop: 8 }}>
              <button className="btn primary" onClick={checkDictation}>检查</button>
              <button className="btn" onClick={() => playTTS(currentSentence.russian)} style={{ marginLeft: 8 }}>再听一次</button>
            </div>
            {dictationResult && (
              <div className={'result ' + (dictationResult.correct ? 'ok' : 'err')}>
                {dictationResult.correct ? '✓ 完全正确！' : '✗ 有错误'}
                {!dictationResult.correct && (
                  <div style={{ marginTop: 4 }}>正确答案：{dictationResult.target}</div>
                )}
              </div>
            )}
          </div>
        )}

        {mode === 'grammar' && (
          <div className="grammar-box">
            {grammarLoading ? (
              <div className="hint">AI 解析中...</div>
            ) : grammar ? (
              <div className="ai-out" dangerouslySetInnerHTML={{ __html: grammar.replace(/\n/g, '<br/>') }} />
            ) : (
              <div className="hint">点击下方「语法解释」按钮调用 AI</div>
            )}
          </div>
        )}
      </div>

      {/* 下半区：操作按钮 */}
      <div className="method-controls">
        <div className="ctrl-row">
          <button className="btn" onClick={goPrev} disabled={curIdx === 0}>← 上一句</button>
          <button className="btn primary" onClick={() => playTTS(currentSentence.russian)}>
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
        <div className="ctrl-row">
          <button className={'btn sm' + (mode === 'recite' ? ' primary' : '')} onClick={startRecite}>🎤 跟读模式</button>
          <button className={'btn sm' + (mode === 'dictate' ? ' primary' : '')} onClick={startDictate}>⌨ 听写模式</button>
          <button className={'btn sm' + (mode === 'memorize' ? ' primary' : '')} onClick={startMemorize}>📝 逐句背诵</button>
          <button className={'btn sm' + (mode === 'grammar' ? ' primary' : '')} onClick={explainGrammar}>📖 语法解释</button>
        </div>
        <div className="ctrl-row mark-row">
          <button className="btn sm" onClick={() => setShowZh(v => !v)}>{showZh ? '隐藏中译' : '显示中译'}</button>
          <button className={'btn sm' + (marks[curIdx] === 'mastered' ? ' primary' : '')} onClick={() => markSentence('mastered')}>✓ 掌握</button>
          <button className={'btn sm' + (marks[curIdx] === 'weak' ? ' danger' : '')} onClick={() => markSentence('weak')}>⚠ 薄弱</button>
          <button className="btn sm" onClick={() => addWord({ word: currentSentence.russian, chinese: currentSentence.chinese, source: 'shang' })}>＋ 生词</button>
        </div>
      </div>
    </div>
  )
}
