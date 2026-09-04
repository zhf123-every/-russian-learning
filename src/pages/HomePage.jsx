import { useNavigate } from 'react-router-dom'

export default function HomePage() {
  const navigate = useNavigate()

  const cards = [
    {
      title: '自定义素材',
      icon: '📹',
      sub: '上传 / 粘贴视频生成学习材料',
      desc: '导入你自己的视频或字幕，自动断句，逐句听写、跟读、循环训练。',
      route: '/custom',
    },
    {
      title: '分级课程',
      icon: '🎓',
      sub: '尚雯婕学习法 · 学习广场',
      desc: '从 A1 到 B2 系统训练短句，或到学习广场浏览精选公开素材。',
      route: '/course',
    },
  ]

  return (
    <div className="landing">
      <div className="landing-head">
        <div className="landing-logo">🎬</div>
        <h1>看视频学俄语</h1>
        <p>选择一种学习方式，开始今天的俄语训练</p>
      </div>
      <div className="landing-cards">
        {cards.map(c => (
          <div
            key={c.title}
            className="landing-card"
            onClick={() => navigate(c.route)}
          >
            <div className="icon">{c.icon}</div>
            <h2>{c.title}</h2>
            <div className="sub">{c.sub}</div>
            <p>{c.desc}</p>
            <div className="go">进入 →</div>
          </div>
        ))}
      </div>
    </div>
  )
}
