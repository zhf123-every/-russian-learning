import { useRef, useState } from 'react'
import { dictation, selfRate } from '../lib/scoring'
import { loopSentence } from '../lib/tts'
import { toast } from '../lib/toast'
import { useSettingsStore } from '../store/settingsStore'

const GRADES = [
  { g: 0, label: '忘记' }, { g: 1, label: '困难' }, { g: 2, label: '犹豫' }, { g: 3, label: '顺利' }
]

export default function StageRecite({ sentence, onScore }) {
  const { settings } = useSettingsStore()
  const recRef = useRef(null)
  const [recogText, setRecogText] = useState('')
  const [listening, setListening] = useState(false)
  const [shang, setShang] = useState(false)

  const SR = window.SpeechRecognition || window.webkitSpeechRecognition

  const startMic = () => {
    if (!SR) { toast('当前浏览器不支持语音识别，请用自评'); return }
    const rec = new SR()
    recRef.current = rec
    rec.lang = 'ru-RU'
    rec.onresult = (e) => {
      const text = Array.from(e.results).map(r => r[0].transcript).join(' ')
      setRecogText(text)
      const score = dictation(text, sentence.russian).score
      onScore(score)
    }
    rec.onend = () => setListening(false)
    setListening(true)
    rec.start()
  }

  const stopMic = () => { recRef.current?.stop(); setListening(false) }

  const startShang = () => {
    setShang(true)
    loopSentence([sentence], 0, settings.loopTimes, { rate: settings.rate, onDone: () => {} })
  }

  return (
    <div>
      <div className="row">
        <button className="btn primary" onClick={listening ? stopMic : startMic}>{listening ? '⏹ 停止' : '🎤 开始跟读'}</button>
        <button className="btn" onClick={startShang}>🦜 尚雯婕模式</button>
      </div>
      {shang && <div className="hint" style={{ marginTop: 8 }}>循环听 {settings.loopTimes} 遍后，跟读并自评</div>}
      {recogText && <div className="hint" style={{ marginTop: 8 }}>识别结果：{recogText}</div>}

      <div className="row" style={{ marginTop: 12 }}>
        {GRADES.map(({ g, label }) => (
          <button key={g} className="grade" onClick={() => onScore(selfRate(g))}>{label}<br /><small>{selfRate(g)}分</small></button>
        ))}
      </div>
    </div>
  )
}
