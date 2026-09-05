import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useSquareStore } from '../store/squareStore'
import { useShangStore } from '../store/shangStore'
import { useAdminStore } from '../store/adminStore'
import { SQUARE_CATEGORIES } from '../data/squareLibrary'
import ContributeModal from '../components/ContributeModal'
import { toast } from '../lib/toast'

export default function SquarePage() {
  const navigate = useNavigate()
  const items = useSquareStore(s => s.items())
  const submitItem = useSquareStore(s => s.submitItem)
  const deleteItem = useSquareStore(s => s.deleteItem)
  const fetchServer = useSquareStore(s => s.fetchServer)
  const shang = useShangStore()
  const adminKey = useAdminStore(s => s.adminKey)
  const adminLogin = useAdminStore(s => s.login)
  const adminLogout = useAdminStore(s => s.logout)
  const isAdmin = !!adminKey
  const [selectedCategory, setSelectedCategory] = useState('all')
  const [showContribute, setShowContribute] = useState(false)
  const [noSubsItem, setNoSubsItem] = useState(null)
  const [showAdmin, setShowAdmin] = useState(false)
  const [adminInput, setAdminInput] = useState('')

  useEffect(() => { fetchServer() }, [fetchServer])

  const filtered = selectedCategory === 'all'
    ? items
    : items.filter(x => x.category === selectedCategory)

  // 尚雯婕学习法入口：校验分句字幕，无字幕弹窗提示并阻止跳转
  const openShang = (item) => {
    const hasSubs = Array.isArray(item.sentences) && item.sentences.length > 0
    if (!hasSubs) {
      setNoSubsItem(item)
      return
    }
    shang.init(item.id)
    navigate(`/square/${item.id}?mode=shang`)
  }

  const doAdminLogin = async () => {
    const ok = await adminLogin(adminInput)
    if (ok) {
      setShowAdmin(false); setAdminInput(''); toast('已进入管理模式')
    } else {
      toast('密钥错误')
    }
  }

  const doDelete = async (item) => {
    if (!window.confirm(`确定删除「${item.title}」？此操作不可撤销。`)) return
    try {
      await deleteItem(item.id, adminKey)
      toast('已删除')
    } catch (e) {
      toast('删除失败：' + (e.message || '请重试'))
    }
  }

  return (
    <div className="course">
      <div className="square-head">
        <button className="btn sm" onClick={() => navigate('/course')}>← 返回分级课程</button>
        <h2>学习广场</h2>
        {isAdmin ? (
          <>
            <button className="btn sm" onClick={() => { adminLogout(); toast('已退出管理模式') }}>退出管理</button>
            <button className="btn primary" onClick={() => setShowContribute(true)}>＋ 上传素材</button>
          </>
        ) : (
          <button className="btn sm" onClick={() => setShowAdmin(true)}>🔐 管理</button>
        )}
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
          <p>{isAdmin ? '点右上角上传第一个素材吧！' : '管理员还没有上传素材，敬请期待。'}</p>
          {isAdmin && (
            <div className="cta">
              <button className="btn primary" onClick={() => setShowContribute(true)}>＋ 上传素材</button>
            </div>
          )}
        </div>
      ) : (
        <div className="videos-grid">
          {filtered.map(item => {
            const hasSubs = Array.isArray(item.sentences) && item.sentences.length > 0
            const finished = shang.isFinished(item.id)
            return (
              <div key={item.id} className="video-card">
                <div className="thumb" style={{ backgroundImage: `url(${item.thumbnail})` }}>
                  <span className="thumb-score">{item.level}</span>
                  {finished && <span className="thumb-score" style={{ background: '#5C8A6B' }}>✓ 尚雯</span>}
                </div>
                <div className="vc-body">
                  <div className="vc-title">{item.title}</div>
                  <div className="vc-meta">👁 {item.views} · 👤 {item.author}</div>
                  <div className="vc-tags">{(item.tags || []).map(t => <span key={t} className="chip">{t}</span>)}</div>
                  <div className="vc-meta" style={{ marginTop: 4, color: hasSubs ? 'var(--accent, #A86454)' : 'var(--muted)' }}>
                    {hasSubs ? `✓ 有分句字幕 ${item.sentences.length} 句` : '✗ 无分句字幕'}
                  </div>
                  <div className="row" style={{ marginTop: 8, gap: 6 }}>
                    <button className="btn sm" onClick={() => navigate(`/square/${item.id}`)}>📖 普通学习</button>
                    <button
                      className="btn sm primary"
                      onClick={() => openShang(item)}
                      disabled={!hasSubs}
                    >🦜 尚雯婕学习法</button>
                    {isAdmin && (
                      <button className="btn sm" onClick={() => doDelete(item)}>🗑 删除</button>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {showContribute && (
        <ContributeModal
          onClose={() => setShowContribute(false)}
          onSubmit={(data) => submitItem(data, adminKey)}
        />
      )}

      {/* 管理员登录弹窗 */}
      {showAdmin && (
        <div className="modal-mask" onClick={() => setShowAdmin(false)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 380 }}>
            <h2>🔐 管理登录</h2>
            <p className="hint">输入管理员密钥以解锁上传 / 删除。</p>
            <div className="field">
              <label>管理员密钥</label>
              <input
                type="password"
                value={adminInput}
                onChange={e => setAdminInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') doAdminLogin() }}
                placeholder="ADMIN_KEY"
                autoFocus
              />
            </div>
            <div className="mfoot">
              <button className="btn" onClick={() => setShowAdmin(false)}>取消</button>
              <button className="btn primary" onClick={doAdminLogin}>登录</button>
            </div>
          </div>
        </div>
      )}

      {/* 缺少分句字幕弹窗：原版硬性规则，阻止跳转 */}
      {noSubsItem && (
        <div className="modal-mask" onClick={() => setNoSubsItem(null)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 420 }}>
            <h2>⚠️ 无法使用尚雯婕学习法</h2>
            <p className="hint" style={{ margin: '12px 0' }}>
              该素材「{noSubsItem.title}」缺少分句字幕，无法使用尚雯婕学习法。
            </p>
            <p className="hint" style={{ margin: 0, fontSize: 13 }}>
              尚雯婕学习法需要逐句分句字幕支持盲听与逐句听写。请先为该素材补充分句字幕后再试。
            </p>
            <div className="mfoot">
              <button className="btn" onClick={() => setNoSubsItem(null)}>我知道了</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
