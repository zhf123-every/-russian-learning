import { Routes, Route, Link, useLocation } from 'react-router-dom'
import Home from './pages/Home'
import Study from './pages/Study'
import Vocab from './pages/Vocab'
import Profile from './pages/Profile'

export default function App() {
  const loc = useLocation()
  return (
    <>
      <div className="topbar">
        <div className="brand"><span className="logo">🎬</span><span>看视频学俄语</span></div>
        {loc.pathname !== '/' && <Link className="tbtn" to="/">🏠 首页</Link>}
        <div className="spacer"></div>
        <Link className="tbtn" to="/vocab">生词本</Link>
        <Link className="tbtn" to="/profile">统计</Link>
      </div>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/study/:videoId" element={<Study />} />
        <Route path="/vocab" element={<Vocab />} />
        <Route path="/profile" element={<Profile />} />
      </Routes>
    </>
  )
}
