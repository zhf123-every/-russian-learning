import { useNavigate } from 'react-router-dom'

export default function CoursePage() {
  const navigate = useNavigate()

  const cards = [
    {
      title: '尚雯婕学习法',
      icon: '🎵',
      sub: '纯听觉 + 文字专注训练',
      desc: 'A1–B2 分级短句，支持变速播放、跟读、听写、逐句背诵与语法解析。',
      route: '/method',
    },
    {
      title: '学习广场',
      icon: '🛍️',
      sub: '精选公开素材',
      desc: '购物、日常、演讲、职场等分类视频，随点随学，人人可投稿。',
      route: '/square',
    },
  ]

  return (
    <div className="course">
      <div className="row" style={{ marginBottom: 16 }}>
        <button className="btn sm" onClick={() => navigate('/')}>← 返回首页</button>
      </div>
      <h2>分级课程</h2>
      <p className="hint">选择一种训练方式</p>
      <div className="home-cards" style={{ marginTop: 8 }}>
        {cards.map(c => (
          <div
            key={c.title}
            className="home-card"
            onClick={() => navigate(c.route)}
          >
            <div className="icon">{c.icon}</div>
            <h2>{c.title}</h2>
            <div className="sub">{c.sub}</div>
            <p>{c.desc}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
