import { useState } from 'react'
import { useSettingsStore } from '../store/settingsStore'
import { exportBackup, importBackup } from '../lib/backup'
import { toast } from '../lib/toast'

export default function SettingsModal({ onClose }) {
  const { settings, save } = useSettingsStore()
  const [s, setS] = useState(settings)

  const set = (k, v) => setS(prev => ({ ...prev, [k]: v }))

  const doExport = () => {
    try {
      exportBackup()
      toast('已导出备份')
    } catch (e) { toast('导出失败：' + e.message) }
  }

  const doImport = (e) => {
    const f = e.target.files?.[0]
    if (!f) return
    const r = new FileReader()
    r.onload = () => {
      try {
        importBackup(r.result)
        toast('已导入备份，刷新页面生效')
      } catch (err) { toast('导入失败：' + err.message) }
    }
    r.readAsText(f)
  }

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>设置</h2>
        <p className="hint">「语法解释 / AI 解析」由服务端密钥统一调用（部署时在环境变量配置）。下方「API Key」仅用于本地「AI 断句」。</p>
        <div className="field"><label>接口地址 baseUrl</label><input value={s.baseUrl} onChange={e => set('baseUrl', e.target.value)} /></div>
        <div className="field"><label>API Key</label><input type="password" value={s.apiKey} onChange={e => set('apiKey', e.target.value)} placeholder="sk-..." /></div>
        <div className="field"><label>模型名</label><input value={s.model} onChange={e => set('model', e.target.value)} /></div>
        <div className="field">
          <label>Whisper 转写模型（「从音频识别字幕」用，纯本地无需 key）</label>
          <select value={s.whisperModel || 'small'} onChange={e => set('whisperModel', e.target.value)}>
            <option value="tiny">tiny —— 最快，错字较多</option>
            <option value="base">base —— 快，一般</option>
            <option value="small">small —— 推荐，质量/速度平衡</option>
            <option value="medium">medium —— 更准，慢、占内存多</option>
          </select>
        </div>
        <div className="field"><label>语速 rate</label><input type="number" step="0.1" min="0.5" max="2" value={s.rate} onChange={e => set('rate', parseFloat(e.target.value) || 1)} /></div>
        <div className="field"><label>尚雯婕模式循环遍数</label><input type="number" min="1" max="10" value={s.loopTimes} onChange={e => set('loopTimes', parseInt(e.target.value) || 3)} /></div>
        <div className="field" style={{ borderTop: '1px solid var(--border)', paddingTop: 12, display: 'flex', gap: 8 }}>
          <button className="btn sm" onClick={doExport}>导出备份</button>
          <button className="btn sm" onClick={() => document.getElementById('impBackup').click()}>导入备份</button>
          <input type="file" id="impBackup" accept=".json" className="hidden" onChange={doImport} />
        </div>
        <div className="mfoot">
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn primary" onClick={() => { save(s); onClose() }}>保存</button>
        </div>
      </div>
    </div>
  )
}
