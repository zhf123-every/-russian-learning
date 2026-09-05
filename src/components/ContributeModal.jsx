import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from '../lib/toast'
import { VIDEO_SOURCES, sourcePlaceholder } from '../lib/videoSources'

const CATEGORIES = ['shopping', 'daily', 'vlog', 'speech', 'intro', 'campus', 'work', 'transport']
const LEVELS = ['A1', 'A2', 'B1', 'B2']

export default function ContributeModal({ onClose, onSubmit }) {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    title: '',
    category: 'shopping',
    level: 'A1',
    source: 'youtube',
    videoUrl: '',
    description: ''
  })
  const [autoGrab, setAutoGrab] = useState(false)   // 默认不抓字幕，只提取视频
  const [manualSubs, setManualSubs] = useState('')   // 手动粘贴字幕（可选）
  const [submitting, setSubmitting] = useState(false)

  const handleChange = (field) => (e) => {
    setForm(prev => ({ ...prev, [field]: e.target.value }))
  }

  const handleSubmit = async () => {
    if (!form.title || !form.videoUrl) {
      toast('请填写标题和视频链接')
      return
    }
    setSubmitting(true)
    try {
      let sentences = []
      let fetchError = ''

      // 字幕优先级：手动粘贴 > 自动抓取 > 无（纯视频）
      if (manualSubs.trim()) {
        const { parseTextToSentences } = await import('../lib/srt')
        const { sentences: parsed } = parseTextToSentences(manualSubs)
        sentences = parsed.map((s, i) => ({ id: i + 1, russian: s.text, chinese: '' }))
      } else if (autoGrab) {
        try {
          const r = await fetch('/api/subs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: form.videoUrl })
          })
          const j = await r.json()
          if (j.ok && j.text) {
            const { parseTextToSentences } = await import('../lib/srt')
            const { sentences: parsed } = parseTextToSentences(j.text)
            sentences = parsed.map((s, i) => ({ id: i + 1, russian: s.text, chinese: '' }))
          } else {
            fetchError = j.error || '未知错误'
          }
        } catch (e) {
          fetchError = e.message
        }
      }

      const id = 'square_' + Date.now()
      const payload = {
        id,
        title: form.title,
        category: form.category,
        level: form.level,
        source: form.source,
        videoUrl: form.videoUrl,
        description: form.description,
        thumbnail: `https://picsum.photos/seed/${id}/400/280`,
        posterUrl: `https://picsum.photos/seed/${id}/1280/720`,
        sentences,
        author: '管理员',
        views: 0,
        createdAt: Date.now(),
        tags: [form.source, form.category, form.level]
      }

      await onSubmit(payload)
      if (fetchError) {
        toast('已投稿（视频可看），但自动抓字幕失败：' + fetchError)
      } else if (sentences.length) {
        toast('投稿成功！已含 ' + sentences.length + ' 句字幕')
      } else {
        toast('投稿成功（纯视频，暂无字幕）')
      }
      onClose()
      navigate('/square')
    } catch (e) {
      toast('投稿失败：' + (e.message || '请重试'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 520 }}>
        <h2>投稿素材</h2>
        <p className="hint">贴链接即可提取视频；字幕可选（自动抓取或手动粘贴），没有也可以先发纯视频。</p>

        <div className="field">
          <label>标题</label>
          <input value={form.title} onChange={handleChange('title')} placeholder="例如：莫斯科地铁站的美丽" />
        </div>

        <div className="field">
          <label>视频来源</label>
          <select value={form.source} onChange={handleChange('source')}>
            {VIDEO_SOURCES.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
        </div>

        <div className="field">
          <label>视频链接</label>
          <input
            value={form.videoUrl}
            onChange={handleChange('videoUrl')}
            placeholder={sourcePlaceholder(form.source)}
          />
        </div>

        <div className="field">
          <label>分类</label>
          <select value={form.category} onChange={handleChange('category')}>
            {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        <div className="field">
          <label>难度</label>
          <select value={form.level} onChange={handleChange('level')}>
            {LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>

        <div className="field">
          <label className="row" style={{ alignItems: 'center', gap: 6 }}>
            <input type="checkbox" checked={autoGrab} onChange={e => setAutoGrab(e.target.checked)} />
            <span>⚡ 自动抓俄语字幕（可选）</span>
          </label>
          <div className="hint" style={{ marginTop: 2 }}>勾选后会自动抓取视频里的俄语字幕（含自动生成字幕）；不勾则只提取视频。</div>
        </div>

        <div className="field">
          <label>手动粘贴字幕（可选，SRT / VTT / 纯文本）</label>
          <textarea
            rows={4}
            value={manualSubs}
            onChange={e => setManualSubs(e.target.value)}
            placeholder={'视频没有俄语字幕时，可在这里粘贴字幕。\n\nSRT 例子：\n1\n00:00:01,000 --> 00:00:04,000\nПривет, как дела?'}
          />
        </div>

        <div className="field">
          <label>描述（可选）</label>
          <textarea
            value={form.description}
            onChange={handleChange('description')}
            placeholder="补充说明，比如场景、学习目标等"
            rows={2}
          />
        </div>

        <div className="mfoot">
          <button className="btn" onClick={onClose} disabled={submitting}>取消</button>
          <button className="btn primary" onClick={handleSubmit} disabled={submitting}>
            {submitting ? '提交中...' : '投稿'}
          </button>
        </div>
      </div>
    </div>
  )
}
