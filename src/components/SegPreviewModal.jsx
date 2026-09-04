import { useState, useEffect } from 'react'
import { aiSegmentFromCues, aiSegmentFromPlain } from '../lib/segmenter'
import { toast } from '../lib/toast'

export default function SegPreviewModal({ sentences, cues, settings, onAccept, onClose }) {
  const [understanding, setUnderstanding] = useState(null)
  const [translations, setTranslations] = useState([])
  const [currentSentences, setCurrentSentences] = useState(sentences || [])
  const [feedback, setFeedback] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  useEffect(() => {
    if (done) return
    // 首次进入时尝试 AI 断句
    runSegmentation('')
    setDone(true)
  }, [])

  const runSegmentation = async (fb) => {
    setBusy(true)
    try {
      let result
      if (cues && cues.length) {
        result = await aiSegmentFromCues(cues, fb, currentSentences, settings)
      } else {
        result = await aiSegmentFromPlain(
          currentSentences.map(s => s.text).join(' '),
          fb,
          settings
        )
      }
      if (result && result.sentences && result.sentences.length) {
        setCurrentSentences(result.sentences)
        setTranslations(result.translations || [])
        if (result.understanding) setUnderstanding(result.understanding)
        toast('已生成 ' + result.sentences.length + ' 句')
      } else {
        toast('AI 断句失败，将使用规则断句结果')
      }
    } catch (e) {
      toast('AI 请求失败：' + e.message)
    } finally {
      setBusy(false)
    }
  }

  const accept = () => {
    onAccept(currentSentences, translations)
  }

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 760 }}>
        <h2>🤖 AI 智能断句预览</h2>
        <p className="hint">
          AI 已根据你的输入完成断句 + 逐句翻译。你可以点击「重新生成」让 AI 按你的意见修改；满意后点「接受并保存」。
        </p>

        {understanding && (
          <div style={{ marginBottom: 12, padding: 10, background: 'var(--bg2)', borderRadius: 8 }}>
            <div style={{ fontSize: 12, color: 'var(--text2)', marginBottom: 4 }}>📖 AI 对全文的理解</div>
            <div style={{ fontSize: 14 }}>{understanding}</div>
          </div>
        )}

        <div style={{ maxHeight: 360, overflowY: 'auto', marginBottom: 12 }}>
          {busy && <div className="ai-loading">🤖 AI 正在断句…</div>}
          {!busy && currentSentences.map((s, i) => (
            <div key={i} style={{ marginBottom: 8, padding: 10, border: '1px solid var(--border)', borderRadius: 8 }}>
              <div style={{ fontSize: 11, color: 'var(--text2)' }}>第 {i + 1} 句</div>
              <div className="ru" style={{ fontSize: 15, fontWeight: 500 }}>{s.text}</div>
              {translations[i] && (
                <div style={{ fontSize: 13, color: 'var(--text2)', marginTop: 4 }}>🇨🇳 {translations[i]}</div>
              )}
              {typeof s.start === 'number' && s.start > 0 && (
                <div style={{ fontSize: 10, color: 'var(--text2)', marginTop: 4 }}>
                  ⏱ {s.start.toFixed(1)}s – {s.end?.toFixed(1)}s
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="field">
          <label>修改意见（可选）</label>
          <textarea
            rows={2}
            value={feedback}
            onChange={e => setFeedback(e.target.value)}
            placeholder="例如：第二句和第三句应该合并成一句"
          />
        </div>

        <div className="mfoot">
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn" disabled={busy} onClick={() => runSegmentation(feedback)}>
            {busy ? '重新生成中…' : '🔄 重新生成'}
          </button>
          <button className="btn primary" disabled={busy} onClick={accept}>
            ✓ 接受并保存
          </button>
        </div>
      </div>
    </div>
  )
}