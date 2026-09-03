import { useState } from 'react'
import { speak, speakAll, loopSentence, cancelSpeech } from '../lib/tts'
import { useSettingsStore } from '../store/settingsStore'

export default function StageListen({ sentences, curIdx, onSetPlaying }) {
  const { settings } = useSettingsStore()
  const [looping, setLooping] = useState(false)

  const voice = undefined // Task 12 接 getRuVoice；先 undefined
  const playOne = () => speak(sentences[curIdx].russian, { rate: settings.rate, onStart: () => onSetPlaying(curIdx), onEnd: () => onSetPlaying(-1) })
  const playAll = () => { cancelSpeech(); speakAll(sentences, { from: curIdx, rate: settings.rate, onIndex: onSetPlaying, onDone: () => onSetPlaying(-1) }) }
  const loop = () => { setLooping(true); loopSentence(sentences, curIdx, settings.loopTimes, { rate: settings.rate, onIndex: onSetPlaying, onDone: () => { onSetPlaying(-1); setLooping(false) } }) }
  const stop = () => { cancelSpeech(); onSetPlaying(-1); setLooping(false) }

  return (
    <div className="row">
      <button className="btn primary" onClick={playOne}>▶ 播放本句</button>
      <button className="btn" onClick={playAll}>▶▶ 全文连播</button>
      <button className="btn" onClick={looping ? stop : loop}>{looping ? '⏹ 停止循环' : `🔁 循环听 ${settings.loopTimes} 遍`}</button>
    </div>
  )
}
