import { useState } from 'react'
import { useSettingsStore } from '../store/settingsStore'
import { parseAIJSON, chat } from '../lib/ai'
import { toast } from '../lib/toast'

const SYSTEM_GENERATE = '你是俄语学习教练。根据课文和学生的生词出一份检测题，检验学生是否真正掌握这篇课文。题目要覆盖：生词含义、关键语法（格/动词变位/体）、句子理解。严格只输出 JSON，不要任何解释。JSON 格式：{"questions":[{"type":"choice","question":"题目（中文，可含俄语）","options":["选项A","选项B","选项C","选项D"],"answer":"正确选项的完整内容"},{"type":"fill","question":"填空或翻译题（中文提示）","answer":"参考答案（俄语）"}]}。共 12-15 题，覆盖尽量多的知识点（生词、变格、变位、体、句子理解），难度适中偏难。'

const SYSTEM_GRADE = '你是俄语学习教练。批改学生的作答，给出科学评估报告。严格只输出 JSON，不要任何解释。JSON 格式：{"assessment_level":"pass 或 review 或 fail","score":0到100的整数,"must_master":["必须掌握的生词/短语"],"weak_grammar":["薄弱语法点"],"suggestions":["具体的俄语学习建议"]}。assessment_level 判断标准（务必非常严格，宁严勿松，不要轻易给 pass）：正确率>=90% 且无任何语法/变格/变位错误=pass；60%-89% 或有一处以上错误=review；<60% 或存在严重错误=fail。'

const LEVEL_MAP = {
  pass: { label: '✅ 通过', color: '#16a34a' },
  review: { label: '⚠️ 需复习', color: '#d97706' },
  fail: { label: '❌ 未通过', color: '#e11d48' },
}

function QuizCard({ q, i, value, onChange }) {
  if (q.type === 'choice') {
    return (
      <div className="qcard">
        <div className="qnum">第 {i + 1} 题 · 选择</div>
        <div className="qtxt">{q.question}</div>
        <div className="qopts">
          {q.options.map((o, j) => (
            <label key={j} className="qopt">
              <input type="radio" name={'q' + i} value={j} checked={value === j} onChange={() => onChange(j)} />
              <span>{o}</span>
            </label>
          ))}
        </div>
      </div>
    )
  }
  return (
    <div className="qcard">
      <div className="qnum">第 {i + 1} 题 · 填空/翻译</div>
      <div className="qtxt">{q.question}</div>
      <input
        type="text"
        className="qfill ru"
        value={value || ''}
        onChange={e => onChange(e.target.value)}
        placeholder="用俄语作答"
      />
    </div>
  )
}

function ReportView({ result, onReset, onNext }) {
  const lm = LEVEL_MAP[result.assessment_level] || { label: '未知', color: '#6b7280' }
  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
        <span style={{ background: lm.color, color: '#fff', padding: '4px 10px', borderRadius: 6, fontSize: 13, fontWeight: 600 }}>{lm.label}</span>
        <span className="score-big">{result.score != null ? result.score + ' 分' : '—'}</span>
      </div>

      <div className="rep-sec">
        <b>🎯 必须掌握：</b>
        {(result.must_master && result.must_master.length)
          ? result.must_master.map((x, i) => <span key={i} className="chip ru">{x}</span>)
          : <span className="hint">无</span>}
      </div>

      <div className="rep-sec">
        <b>⚠️ 薄弱语法点：</b>
        <ul className="rep-ul">
          {(result.weak_grammar && result.weak_grammar.length)
            ? result.weak_grammar.map((x, i) => <li key={i}>{x}</li>)
            : <li>无</li>}
        </ul>
      </div>

      <div className="rep-sec">
        <b>📚 俄语学习建议：</b>
        <ul className="rep-ul">
          {(result.suggestions && result.suggestions.length)
            ? result.suggestions.map((x, i) => <li key={i}>{x}</li>)
            : <li>—</li>}
        </ul>
      </div>

      <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
        <button className="btn" onClick={onReset}>🔄 重新检测</button>
        {result.assessment_level === 'pass'
          ? <button className="btn primary" onClick={onNext}>进入下一篇 →</button>
          : <span className="hint" style={{ alignSelf: 'center' }}>⛔ 未通过检测，请复习本篇并重新检测后再进入下一篇</span>}
      </div>
    </>
  )
}

export default function CoachModal({ sentences, onClose, onNext }) {
  const [phase, setPhase] = useState('idle') // idle | loading | quiz | grading | report
  const [quiz, setQuiz] = useState(null)
  const [answers, setAnswers] = useState([])
  const [result, setResult] = useState(null)

  const settings = useSettingsStore(s => s.settings)

  const lessonText = sentences.map(s => s.text || s.russian).join('\n')

  const start = async () => {
    if (!settings.apiKey) { toast('请先在「设置」里填写 API Key'); return }
    setPhase('loading')
    try {
      const res = await chat({ ...settings, messages: [
        { role: 'system', content: SYSTEM_GENERATE },
        { role: 'user', content: '课文全文：\n' + lessonText }
      ] })
      const parsed = parseAIJSON(res)
      if (!parsed || !parsed.questions?.length) { toast('出题失败，请重试'); setPhase('idle'); return }
      setQuiz(parsed)
      setAnswers(new Array(parsed.questions.length).fill(null))
      setPhase('quiz')
    } catch (e) { toast('出题失败：' + e.message); setPhase('idle') }
  }

  const submit = async () => {
    setPhase('grading')
    try {
      const res = await chat({ ...settings, messages: [
        { role: 'system', content: SYSTEM_GRADE },
        { role: 'user', content: '题目：' + JSON.stringify(quiz.questions) + '\n\n学生作答：' + JSON.stringify(answers) }
      ] })
      const parsed = parseAIJSON(res)
      if (!parsed) { toast('批改失败，请重试'); setPhase('quiz'); return }
      setResult(parsed)
      setPhase('report')
    } catch (e) { toast('批改失败：' + e.message); setPhase('quiz') }
  }

  const reset = () => {
    setPhase('idle'); setQuiz(null); setAnswers([]); setResult(null)
  }

  const updateAnswer = (i, val) => {
    setAnswers(prev => { const n = [...prev]; n[i] = val; return n })
  }

  const renderBody = () => {
    if (phase === 'idle') {
      return (
        <>
          <p className="hint" style={{ margin: '0 0 10px' }}>完成本篇「听→听写→跟读」后做一次检测，检验是否真正掌握。</p>
          <button className="btn primary" onClick={start}>🚀 开始本篇学习检测</button>
        </>
      )
    }
    if (phase === 'loading') {
      return <div className="ai-loading">AI 教练正在根据课文和你的生词出题…</div>
    }
    if (phase === 'grading') {
      return <div className="ai-loading">AI 教练正在批改你的作答…</div>
    }
    if (phase === 'quiz' && quiz) {
      return (
        <>
          {quiz.questions.map((q, i) => (
            <QuizCard key={i} q={q} i={i} value={answers[i]} onChange={val => updateAnswer(i, val)} />
          ))}
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <button className="btn primary" onClick={submit}>📝 提交作答</button>
            <button className="btn" onClick={reset}>重新检测</button>
          </div>
        </>
      )
    }
    if (phase === 'report' && result) {
      return (
        <ReportView
          result={result}
          onReset={reset}
          onNext={() => { onClose(); if (onNext) onNext() }}
        />
      )
    }
    return null
  }

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 680 }}>
        <h2>🤖 AI 学习教练</h2>
        {renderBody()}
        <div className="mfoot">
          <button className="btn" onClick={onClose}>关闭</button>
        </div>
      </div>
    </div>
  )
}
