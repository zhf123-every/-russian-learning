import { useState } from 'react'
import { useSettingsStore } from '../store/settingsStore'

export default function SettingsModal({ onClose }) {
  const { settings, save } = useSettingsStore()
  const [s, setS] = useState(settings)

  const set = (k, v) => setS(prev => ({ ...prev, [k]: v }))

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>设置</h2>
        <p className="hint">「AI 解析」需配置 OpenAI 兼容接口（DeepSeek / 通义 / 智谱等）。</p>
        <div className="field"><label>接口地址 baseUrl</label><input value={s.baseUrl} onChange={e => set('baseUrl', e.target.value)} /></div>
        <div className="field"><label>API Key</label><input type="password" value={s.apiKey} onChange={e => set('apiKey', e.target.value)} placeholder="sk-..." /></div>
        <div className="field"><label>模型名</label><input value={s.model} onChange={e => set('model', e.target.value)} /></div>
        <div className="field"><label>语速 rate</label><input type="number" step="0.1" min="0.5" max="2" value={s.rate} onChange={e => set('rate', parseFloat(e.target.value) || 1)} /></div>
        <div className="field"><label>尚雯婕模式循环遍数</label><input type="number" min="1" max="10" value={s.loopTimes} onChange={e => set('loopTimes', parseInt(e.target.value) || 3)} /></div>
        <div className="mfoot">
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn primary" onClick={() => { save(s); onClose() }}>保存</button>
        </div>
      </div>
    </div>
  )
}
