import { useState, useEffect } from 'react'
import { mdToHtml } from '../lib/md'

// 从全局变量加载语法数据
const RU_GRAMMAR = typeof window !== 'undefined' ? (window.RU_GRAMMAR || []) : []

function GrammarItem({ item }) {
  if (item.type === 'table') {
    return (
      <div className="gitem">
        {item.label && <div className="glabel">{item.label}</div>}
        <div style={{ overflowX: 'auto' }}>
          <table className="gtable">
            <thead>
              <tr>{item.head.map((h, i) => <th key={i}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {item.rows.map((row, i) => (
                <tr key={i}>{row.map((c, j) => <td key={j} dangerouslySetInnerHTML={{ __html: mdToHtml(c) }} />)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )
  }
  if (item.type === 'text') {
    return <div className="gtext" dangerouslySetInnerHTML={{ __html: mdToHtml(item.html) }} />
  }
  return null
}

export default function GrammarModal({ onClose }) {
  const [active, setActive] = useState(0)
  const [q, setQ] = useState('')

  const hits = q.trim()
    ? RU_GRAMMAR.reduce((acc, g, gi) => {
        const titleHit = g.title.toLowerCase().includes(q.toLowerCase())
        const introHit = (g.intro || '').toLowerCase().includes(q.toLowerCase())
        const itemHit = g.items.some(it => {
          if (it.label?.toLowerCase().includes(q.toLowerCase())) return true
          if (it.type === 'table') {
            return [...(it.head || []), ...(it.rows?.flat() || [])].some(c => String(c).toLowerCase().includes(q.toLowerCase()))
          }
          return it.html?.toLowerCase().includes(q.toLowerCase())
        })
        if (titleHit || introHit || itemHit) acc.push({ gi, title: g.title })
        return acc
      }, [])
    : []

  const current = RU_GRAMMAR[active]

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 960 }}>
        <h2>📚 俄语语法工具书</h2>
        <div className="row" style={{ marginBottom: 12 }}>
          <input
            className="qfill"
            placeholder="🔍 搜索语法：名词变格、动词时态…"
            value={q}
            onChange={e => setQ(e.target.value)}
          />
        </div>

        {hits.length > 0 && (
          <div style={{ marginBottom: 12, maxHeight: 160, overflowY: 'auto', border: '1px solid var(--border2)', borderRadius: 8, padding: 8 }}>
            <div className="hint" style={{ margin: 0 }}>搜索「{q}」找到 {hits.length} 个相关章节：</div>
            {hits.map(h => (
              <div key={h.gi} className="gnav-item"
                style={{ border: '1px solid var(--border2)', padding: 8, marginTop: 6, cursor: 'pointer' }}
                onClick={() => { setActive(h.gi); setQ('') }}>
                {h.title}
              </div>
            ))}
          </div>
        )}

        <div className="grammar-layout" style={{ display: 'flex', gap: 16 }}>
          <div style={{ width: 170, flexShrink: 0, maxHeight: '66vh', overflowY: 'auto' }}>
            {RU_GRAMMAR.map((g, i) => (
              <div key={g.id || i}
                className={'gnav-item' + (i === active && !q ? ' active' : '')}
                onClick={() => { setActive(i); setQ('') }}>
                {g.title}
              </div>
            ))}
          </div>
          <div style={{ flex: 1, minWidth: 0, maxHeight: '66vh', overflowY: 'auto', paddingRight: 4 }}>
            {current && (
              <>
                {current.intro && (
                  <div className="ginto" dangerouslySetInnerHTML={{ __html: mdToHtml(current.intro) }} />
                )}
                {current.items.map((item, i) => <GrammarItem key={i} item={item} />)}
              </>
            )}
          </div>
        </div>

        <div className="mfoot">
          <button className="btn" onClick={onClose}>关闭</button>
        </div>
      </div>
    </div>
  )
}