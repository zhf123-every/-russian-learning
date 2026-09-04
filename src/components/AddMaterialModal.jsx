import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useCourseStore } from '../store/courseStore'
import { useSettingsStore } from '../store/settingsStore'
import { toast } from '../lib/toast'
import SegPreviewModal from './SegPreviewModal'

const DEMO_TEXT = `Привет, меня зовут Иван. Я живу в Москве.
Каждый день я встаю в шесть утра и иду на работу.
Моя работа очень интересная, я работаю программистом.
В свободное время я люблю читать книги и слушать музыку.
По вечерам я обычно готовлю ужин и смотрю фильмы.
Мой любимый фильм — это «Сталкер» Андрея Тарковского.
Я думаю, что жизнь прекрасна, и я хочу путешествовать по миру.`

export default function AddMaterialModal({ onClose }) {
  const navigate = useNavigate()
  const addMaterial = useCourseStore(s => s.addMaterial)
  const settings = useSettingsStore(s => s.settings)
  const [type, setType] = useState('youtube') // 'youtube' | 'local'
  const [url, setUrl] = useState('')
  const [file, setFile] = useState(null)
  const [subs, setSubs] = useState('')
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [preview, setPreview] = useState(null) // { sentences, cues, hasTimestamps }
  const fileRef = useRef()

  const loadDemo = () => {
    setSubs(DEMO_TEXT)
    if (!title) setTitle('示例数据：俄语自我介绍')
    toast('已加载示例文本')
  }

  const fetchSubs = async () => {
    if (!url.trim()) { toast('请先填写 YouTube 链接'); return }
    setBusy(true)
    try {
      const r = await fetch('/api/subs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url.trim() })
      })
      const j = await r.json()
      if (!j.ok) { toast('抓字幕失败：' + (j.error || '未知错误')); return }
      setSubs(j.text || '')
      toast('已抓取字幕，共 ' + (j.cues?.length || 0) + ' 条')
    } catch (e) {
      toast('请求失败：' + e.message)
    } finally {
      setBusy(false)
    }
  }

  const onFile = (e) => {
    const f = e.target.files?.[0]
    if (!f) return
    setFile(f)
    // 同时读字幕文本（如有）
    const r = new FileReader()
    r.onload = () => setSubs(String(r.result || ''))
    r.readAsText(f)
    if (!title) setTitle(f.name.replace(/\.[^.]+$/, ''))
  }

  const save = async () => {
    if (!subs.trim()) { toast('请粘贴或抓取字幕'); return }
    setBusy(true)

    // 本地解析（无需网络）
    const { parseTextToSentences } = await import('../lib/srt')
    const { sentences, hasTimestamps } = parseTextToSentences(subs)

    // 有 API Key 且无时间戳 → 走 AI 断句预览
    if (settings.apiKey && !hasTimestamps && sentences.length > 0) {
      setBusy(false)
      setPreview({ sentences, cues: null, hasTimestamps })
      return
    }

    finishImport(sentences, [])
  }

  const finishImport = (sentences, translations) => {
    if (!sentences.length) { toast('未能解析出任何句子'); return }
    const id = 'custom_' + Date.now().toString(36)
    const wordCount = sentences.reduce((n, s) => n + s.text.trim().split(/\s+/).length, 0)
    const enriched = sentences.map((s, i) => ({
      ...s,
      id: i + 1,
      tr: translations[i] || ''
    }))
    addMaterial({
      id,
      title: title.trim() || '自定义文本',
      sentences: enriched,
      createdAt: Date.now(),
      thumbnail: 'https://picsum.photos/seed/' + id + '/400/280',
      posterUrl: 'https://picsum.photos/seed/' + id + '/1280/720',
      tags: ['自定义'],
      duration: '—',
      words: wordCount,
      level: '自定义',
      ...(type === 'youtube' && url ? { videoUrl: url.trim() } : {}),
      ...(type === 'local' && file ? { videoFileName: file.name, videoFileType: file.type } : {}),
    })
    toast('已保存，开始学习')
    navigate('/study/' + id)
  }

  return (
    <>
      <div className="modal-mask" onClick={onClose}>
        <div className="modal" onClick={e => e.stopPropagation()}>
          <h2>＋ 导入材料</h2>
          <p className="hint">
            一个「材料」= 视频 + 字幕。字幕会拆成一句句台词，供你逐句学习。<br />
            📌 点击「保存并开始学习」时，若有 API Key 且无时间戳，会用 AI 智能断句并弹出预览窗口；否则用规则断句（cue 边界 + 标点）后直接保存。
          </p>

          <div className="field">
            <label>① 视频来源</label>
            <select value={type} onChange={e => setType(e.target.value)}>
              <option value="youtube">YouTube 链接</option>
              <option value="local">本地视频文件</option>
            </select>
          </div>

          {type === 'youtube' && (
            <div className="field">
              <label>YouTube 链接</label>
              <input
                value={url}
                onChange={e => setUrl(e.target.value)}
                placeholder="https://www.youtube.com/watch?v=..."
              />
              <div className="hint" style={{ marginTop: 4 }}>
                贴链接后点「⚡ 自动抓字幕」即可（会下载俄语字幕，含自动生成字幕）。
              </div>
            </div>
          )}

          {type === 'local' && (
            <div className="field">
              <label>本地视频文件（保存在本机浏览器内，可跨会话）</label>
              <input ref={fileRef} type="file" accept="video/*" onChange={onFile} />
            </div>
          )}

          <div className="field">
            <label>② 字幕（SRT / VTT / 纯文本）</label>
            <textarea
              rows={8}
              value={subs}
              onChange={e => setSubs(e.target.value)}
              placeholder={'粘贴 SRT/VTT 字幕，或纯俄语文本。\n\nSRT 例子：\n1\n00:00:01,000 --> 00:00:04,000\nПривет, как дела?'}
            />
            <div className="row" style={{ marginTop: 6 }}>
              <button className="btn sm" disabled={busy} onClick={fetchSubs}>
                ⚡ 自动抓字幕
              </button>
              <button className="btn sm" onClick={loadDemo}>用示例数据试试</button>
            </div>
          </div>

          <div className="field">
            <label>标题（可选）</label>
            <input value={title} onChange={e => setTitle(e.target.value)} placeholder="例如：俄语日常对话第 1 集" />
          </div>

          <div className="mfoot">
            <button className="btn" onClick={onClose}>取消</button>
            <button className="btn primary" disabled={busy} onClick={save}>
              {busy ? '处理中…' : '保存并开始学习'}
            </button>
          </div>
        </div>
      </div>

      {preview && (
        <SegPreviewModal
          sentences={preview.sentences}
          cues={preview.cues}
          settings={settings}
          onAccept={(sents, translations) => {
            setPreview(null)
            finishImport(sents, translations)
          }}
          onClose={() => {
            // 取消预览时直接用规则断句结果继续
            setPreview(null)
            const { sentences } = preview
            finishImport(sentences, [])
          }}
        />
      )}
    </>
  )
}