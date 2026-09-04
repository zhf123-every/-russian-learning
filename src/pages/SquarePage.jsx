import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useSquareStore } from '../store/squareStore'
import { SQUARE_CATEGORIES } from '../data/squareLibrary'

export default function SquarePage() {
  const navigate = useNavigate()
  const items = useSquareStore(s => s.items())
  const [selectedCategory, setSelectedCategory] = useState('all')

  const filtered = selectedCategory === 'all'
    ? items
    : items.filter(x => x.category === selectedCategory)

  return (
    <div className="course">
      <div className="square-head">
        <button className="btn sm" onClick={() => navigate('/course')}>← 返回分级课程</button>
        <h2>学习广场</h2>
      </div>

      <div className="square-cats">
        <button
          className={'cat' + (selectedCategory === 'all' ? ' active' : '')}
          onClick={() => setSelectedCategory('all')}
        >全部</button>
        {SQUARE_CATEGORIES.map(c => (
          <button
            key={c.key}
            className={'cat' + (selectedCategory === c.key ? ' active' : '')}
            onClick={() => setSelectedCategory(c.key)}
          >
            <span>{c.icon}</span>{c.label}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="empty">
          <div className="big">🛍️</div>
          <h1>这个分类还没有素材</h1>
          <p>敬请期待更多内容</p>
        </div>
      ) : (
        <div className="videos-grid">
          {filtered.map(item => (
            <div key={item.id} className="video-card" onClick={() => navigate('/square/' + item.id)}>
              <div className="thumb" style={{ backgroundImage: `url(${item.thumbnail})` }}>
                <span className="thumb-score">{item.level}</span>
              </div>
              <div className="vc-body">
                <div className="vc-title">{item.title}</div>
                <div className="vc-meta">👁 {item.views} · 👤 {item.author}</div>
                <div className="vc-tags">{(item.tags || []).map(t => <span key={t} className="chip">{t}</span>)}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
