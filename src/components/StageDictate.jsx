import { useState } from 'react'
import { dictation } from '../lib/scoring'
import { speak } from '../lib/tts'
import { useSettingsStore } from '../store/settingsStore'

export default function StageDictate({ sentence, onScore }) {
  const { settings } = useSettingsStore()
  const [input, setInput] = useState('')
  const [result, setResult] = useState(null)

  const submit = () => {
    const r = dictation(input, sentence.russian)
    setResult(r)
    onScore(r.score)
  }

  const replay = () => speak(sentence.russian, { rate: settings.rate })

  return (
    <div>
      <textarea className="dict-area" placeholder="听写这句话…（输入俄语）" value={input} onChange={e => setInput(e.target.value)} />
      <div className="row" style={{ marginTop: 8 }}>
        <button className="btn primary" onClick={submit}>提交</button>
        <button className="btn sm" onClick={replay}>🔊 重听</button>
      </div>
      {result && (
        <div style={{ marginTop: 12 }}>
          <div className="diff-out">
            {result.diff.map((d, i) => <span key={i} className={d.ok ? 'ok' : 'bad'}>{d.word}{i < result.diff.length - 1 ? ' ' : ''}</span>)}
          </div>
          <div className="score">{result.score} 分 {result.score >= 80 ? '✅' : result.score >= 50 ? '👍' : '💪'}</div>
        </div>
      )}
    </div>
  )
}
