import { useState } from 'react'
import { Routes, Route, Link, useLocation } from 'react-router-dom'
import HomePage from './pages/HomePage'
import CoursePage from './pages/CoursePage'
import CustomMaterials from './pages/CustomMaterials'
import ShangMethod from './pages/ShangMethod'
import SquarePage from './pages/SquarePage'
import Study from './pages/Study'
import Vocab from './pages/Vocab'
import Profile from './pages/Profile'
import SettingsModal from './components/SettingsModal'

export default function App() {
  const loc = useLocation()
  const [showSettings, setShowSettings] = useState(false)
  return (
    <>
      <div className="topbar">
        <div className="brand"><span className="logo">🎬</span><span>看视频学俄语</span></div>
        {loc.pathname !== '/' && <Link className="tbtn" to="/">🏠 首页</Link>}
        <div className="spacer"></div>
        <Link className="tbtn" to="/vocab">生词本</Link>
        <Link className="tbtn" to="/profile">统计</Link>
        <button className="tbtn" onClick={() => setShowSettings(true)}>设置</button>
      </div>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/course" element={<CoursePage />} />
        <Route path="/custom" element={<CustomMaterials />} />
        <Route path="/method" element={<ShangMethod />} />
        <Route path="/method/:level" element={<ShangMethod />} />
        <Route path="/square" element={<SquarePage />} />
        <Route path="/square/:id" element={<Study />} />
        <Route path="/study/:videoId" element={<Study />} />
        <Route path="/vocab" element={<Vocab />} />
        <Route path="/profile" element={<Profile />} />
      </Routes>
      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
    </>
  )
}
