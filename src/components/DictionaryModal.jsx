import { useState } from 'react'
import { useCourseStore } from '../store/courseStore'
import { useNavigate } from 'react-router-dom'
import { normWord, findLemma, getZh, getPos, getEntry } from '../lib/lemma'
import { RU_DICT, RU_DICT_FULL } from '../lib/lemma'
import { toast } from '../lib/toast'

export default function DictionaryModal({ onClose }) {
  const [query, setQuery] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [showAI, setShowAI] = useState(false)

  const search = async () => {
    if (!query.trim()) { toast('请先输入俄语单词或变型'); return }
    setLoading(true)
    setResult(null)
    setShowAI(false)

    const w = query.trim()
    // 查找 lemma
    const lemma = findLemma(w)
    let entry = null
    if (lemma) {
      // 优先全词典
      entry = getEntry(w)
    }

    if (entry) {
      setResult({
        word: w,
        lemma: entry.lemma,
        pos: entry.p,
        zh: entry.z || entry.e,
        forms: entry.f || null,
        source: entry.source
      })
    } else {
      // 联网查询
      try {
        const r = await fetch('/api/dict', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ word: w })
        })
        const j = await r.json()
        if (j.ok && j.translation) {
          setResult({ word: w, zh: j.translation, source: 'network' })
        } else {
          toast('未找到翻译')
        }
      } catch (e) {
        toast('查询失败')
      }
    }
    setLoading(false)
  }

  const posLabel = (p) => {
    const map = {
      '代': '代词', '疑': '疑问词', '疑/连': '疑问/连词', '数': '数词', '数/形': '数/形容词',
      '动': '动词', '动·未': '动词（未完成体）', '动·完': '动词（完成体）',
      '名·阳': '名词（阳性）', '名·阴': '名词（阴性）', '名·中': '名词（中性）', '名': '名词',
      '副/名': '副词/名词', '形': '形容词'
    }
    return map[p] || p || '——'
  }

  const entryFormsText = (f) => {
    if (!f || !f.m) return ''
    const c = ['主格', '属格', '与格', '宾格', '工具格', '前置格']
    return c.map((x, i) => `${x}：${f.m[i]}（阳）/${f.f[i]}（阴）/${f.n[i]}（中）/${f.pl[i]}（复）`).join('；')
  }

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 720 }}>
        <h2>📖 俄语词典</h2>
        <p className="hint">内置高频词库（俄→中），可识别常见变格/变位形式；未收录的词自动联网查询。</p>
        <div className="row" style={{ marginBottom: 12 }}>
          <input
            className="qfill"
            placeholder="输入俄语单词，如 стол / делаю / книги"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && search()}
          />
          <button className="btn primary" disabled={loading} onClick={search}>
            {loading ? '查询中…' : '查询'}
          </button>
        </div>

        {result && (
          <div className="field" style={{ marginTop: 0 }}>
            <label>查询结果：</label>
            <div style={{ border: '1px solid var(--border)', borderRadius: 8, padding: 12, background: 'var(--bg2)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <strong>{result.word}</strong>
                <span style={{ fontSize: 12, color: 'var(--text2)' }}>{result.source === 'full' ? '全词典' : result.source === 'basic' ? '简版' : '联网'}</span>
              </div>
              {result.lemma && (
                <div style={{ marginBottom: 6 }}>
                  <span style={{ fontSize: 12, color: 'var(--text2)' }}>词典词：{result.lemma}</span>
                  {result.pos && (
                    <span style={{ marginLeft: 8, fontSize: 12, color: '#666' }}>{posLabel(result.pos)}</span>
                  )}
                </div>
              )}
              {result.zh && (
                <div style={{ fontSize: 15, marginBottom: 12 }}>{result.zh}</div>
              )}
              {result.forms && (
                <div>
                  <div style={{ fontSize: 12, color: 'var(--text2)', marginBottom: 6 }}>变格/变位：</div>
                  <div style={{ fontSize: 13, fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>{entryFormsText(result.forms)}</div>
                </div>
              )}
              {result.word && !result.lemma && !result.zh && (
                <div style={{ color: 'var(--danger)', fontSize: 13 }}>未找到翻译</div>
              )}
              {(result.source === 'full' || result.source === 'basic') && (
                <div style={{ marginTop: 12, borderTop: '1px solid var(--border)', paddingTop: 8 }}>
                  <button className="btn sm primary" onClick={() => setShowAI(!showAI)}>
                    🤖 AI 助教：这是几格？为什么用这个语法？
                  </button>
                  {showAI && (
                    <div style={{ marginTop: 12, padding: 10, background: 'var(--bg)', borderRadius: 8 }}>
                      <div className="ai-loading">AI 助教正在讲解…</div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        <div className="mfoot">
          <button className="btn" onClick={onClose}>关闭</button>
        </div>
      </div>
    </div>
  )
}