import { useState } from 'react'
import { useCourseStore } from '../store/courseStore'
import { useSettingsStore } from '../store/settingsStore'
import { useNavigate } from 'react-router-dom'
import { toast } from '../lib/toast'

function extractYtId(url) {
  const m = url.match(/(?:v=|youtu\.be\/|shorts\/|embed\/)([A-Za-z0-9_-]{11})/)
  return m ? m[1] : null
}

export default function TranscribeModal({ onClose }) {
  const navigate = useNavigate()
  const addMaterial = useCourseStore(s => s.addMaterial)
  const settings = useSettingsStore(s => s.settings)
  const [url, setUrl] = useState('')
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')
  const [segs, setSegs] = useState([])
  const [showPreview, setShowPreview] = useState(false)

  const start = async () => {
    if (!url.trim()) { toast('请先粘贴视频链接'); return }
    setBusy(true)
    setStatus('正在下载音频并识别（可能要几分钟）…')
    try {
      const model = settings.whisperModel || 'small'
      const r = await fetch('/api/transcribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim(), model })
      })
      const j = await r.json()
      if (!j.ok) { alert('识别失败：\n\n' + (j.error || '')); return }
      if (!j.segments || !j.segments.length) { alert('没有识别出任何句子。'); return }
      setSegs(j.segments)
      setStatus('✅ 识别完成，共 ' + j.segments.length + ' 句')
      setShowPreview(true)
    } catch (e) {
      alert('请求失败：请确认本地服务已启动（python server.py）')
    } finally {
      setBusy(false)
    }
  }

  const save = () => {
    if (!segs.length) { toast('请先完成识别'); return }
    const id = extractYtId(url)
    if (!id) { toast('无法识别该视频链接'); return }
    const id2 = 'custom_' + Date.now().toString(36)
    addMaterial({
      id: id2,
      title: title.trim() || '材料 ' + (segs.length + 1),
      type: 'youtube',
      youtubeId: id,
      sentences: segs.map((s, i) => ({ ...s, id: i + 1 })),
      createdAt: Date.now(),
      thumbnail: 'https://picsum.photos/seed/' + id2 + '/400/280',
      posterUrl: 'https://picsum.photos/seed/' + id2 + '/1280/720',
      tags: ['转写'],
      duration: '—',
      words: segs.reduce((n, s) => n + s.text.trim().split(/\s+/).length, 0),
      level: '自定义',
    })
    toast('已导入 ' + segs.length + ' 句，开始学习吧')
    navigate('/study/' + id2)
  }

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>🎙 音频识别</h2>
        <p className="hint">
          粘贴 YouTube 视频链接，后端用 faster-whisper 将整段音频转写为带时间戳的俄语句子。
          模型：{settings.whisperModel || 'small'}（可在设置中调整）
        </p>

        <div className="field">
          <label>视频链接</label>
          <input
            value={url}
            onChange={e => setUrl(e.target.value)}
            placeholder="https://www.youtube.com/watch?v=..."
          />
        </div>

        <div className="field">
          <label>标题（可选）</label>
          <input value={title} onChange={e => setTitle(e.target.value)} placeholder="例如：俄语日常对话第 1 集" />
        </div>

        {status && (
          <div className="hint" style={{ margin: 0 }}>{status}</div>
        )}

        {showPreview && (
          <div className="field">
            <label>识别结果（可直接保存）</label>
            <div style={{ maxHeight: 240, overflowY: 'auto', border: '1px solid var(--border)', borderRadius: 8, padding: 8 }}>
              {segs.map((s, i) => (
                <div key={i} className="sent" style={{ marginBottom: 6 }}>
                  <span className="idx">{i + 1}</span>
                  <span className="ru" style={{ flex: 1 }}>{s.text}</span>
                  <span className="idx">⏱ {s.start.toFixed(1)}s–{s.end.toFixed(1)}s</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="mfoot">
          <button className="btn" onClick={onClose}>关闭</button>
          <button className="btn" disabled={busy} onClick={() => { setUrl('https://www.youtube.com/watch?v=dQw4w9WgXcQ'); setTitle('示例：俄语自我介绍'); toast('已填入示例链接') }}>用示例试试</button>
          <button className="btn primary" disabled={busy} onClick={busy ? undefined : start}>
            {busy ? '🎙 转写中…' : '🎙 开始识别'}
          </button>
          {showPreview && (
            <button className="btn primary" onClick={save}>保存并开始学习</button>
          )}
        </div>
      </div>
    </div>
  )
}