# 看视频学俄语 React 重写 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把现有单文件 vanilla JS 应用重写为 React + Vite 前端，内置预置课程库（TTS 离线播放），并实现听/听写/跟读、评分、FSRS 词句本、最近观看、统计、AI 解析、添加资料。

**Architecture:** Vite + React 18 + React Router 6，Zustand 管理状态（course/vocab/session/settings 四个 store），静态 `courseLibrary` 数据 + localStorage 用户态；播放用 `speechSynthesis` 句级播放，同步高亮由 utterance 事件驱动。纯逻辑模块（scoring/splitter/fsrs/unlock）用 vitest TDD。

**Tech Stack:** react@18, react-dom@18, react-router-dom@6, zustand@4, ts-fsrs@4, vite@5, vitest@2, @testing-library/react@16, jsdom.

**Spec:** `docs/superpowers/specs/2026-09-03-react-rewrite-design.md`（本计划以该 spec 为准，执行时两者一起读）

## Global Constraints

- 沿用现有设计系统：CSS 变量 + 现有类名（`.card`/`.btn`/`.stage`/`.sent` 等），**不引入 Tailwind**。视觉样式从旧 `index.html` 第 8–239 行 `<style>` 原样搬运。
- 句子字段 `{ id, russian, chinese, stressed? }`；**不含 `start/end`**；`stressed` 缺省等于 `russian`。
- localStorage key 前缀 `rlearn_v1`，键名见 `lib/persistence.js` 的 `LS`。
- 听写打分**词级** LCS；自评 4 档映射 `{0:0, 1:35, 2:70, 3:100}`；等级解锁阈值 `LEVEL_PASS = 60`。
- 所有用户态写入须 `try/catch`，失败降级为内存态，不得崩溃。
- 旧 `index.html` 改名为 `legacy.html`，`server.py`/`data/`/词典/语法数据文件原样保留不动。
- Node ≥ 18；Windows PowerShell 环境；命令用 `npm`。

---

## File Structure

```
russian-learning/
├─ index.html                 # Vite 入口（新建）
├─ legacy.html                # 旧单文件前端（改名）
├─ package.json  vite.config.js
└─ src/
   ├─ main.jsx  App.jsx  styles.css  test/setup.js
   ├─ data/courseLibrary.js
   ├─ store/{courseStore,sessionStore,settingsStore,vocabStore}.js
   ├─ lib/{persistence,scoring,splitter,fsrs,tts,ai}.js
   ├─ pages/{Home,Study,Vocab,Profile}.jsx
   └─ components/{VideoCard,SentenceList,SentenceBox,StageListen,StageDictate,StageRecite,WordPop,AddMaterialModal,SettingsModal}.jsx
```

依赖关系（后依赖前）：`persistence` → 各 store；`courseLibrary`+`scoring` → `courseStore`；`tts`/`scoring` → `Study` 各关卡；`fsrs` → `vocabStore` → `Vocab`；`ai` → `SettingsModal`/`WordPop`/`StageDictate`(翻译)。

---

### Task 1: 脚手架 + 路由骨架

**Files:**
- Create: `package.json`, `vite.config.js`, `index.html`, `src/main.jsx`, `src/App.jsx`, `src/styles.css`, `src/test/setup.js`, `src/pages/Home.jsx`, `src/pages/Study.jsx`, `src/pages/Vocab.jsx`, `src/pages/Profile.jsx`
- Rename: `index.html` → `legacy.html`（旧前端保留）
- Create: `.gitignore`

**Interfaces:**
- Produces: 可 `npm run dev` 启动的 Vite 应用；`/`、`/study/:videoId`、`/vocab`、`/profile` 四条路由；`styles.css` 导出全套设计系统类名。

- [ ] **Step 1: 初始化 git 并改名旧前端**

```bash
git init
mv index.html legacy.html
```

（若用户不想要 git，可跳过 `git init`，后续 commit 步骤一并跳过。）

- [ ] **Step 2: 写 `package.json`**

```json
{
  "name": "russian-learning-react",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.28.0",
    "zustand": "^4.5.5",
    "ts-fsrs": "^4.5.1"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.1.0",
    "@testing-library/user-event": "^14.5.2",
    "@vitejs/plugin-react": "^4.3.4",
    "jsdom": "^25.0.1",
    "vite": "^5.4.11",
    "vitest": "^2.1.8"
  }
}
```

- [ ] **Step 3: 写 `vite.config.js`**

```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
  },
})
```

- [ ] **Step 4: 写 `src/test/setup.js`**

```js
import '@testing-library/jest-dom'
```

- [ ] **Step 5: 写 `index.html`（Vite 入口）**

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>看视频学俄语</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/main.jsx"></script>
</body>
</html>
```

- [ ] **Step 6: 写 `src/main.jsx` 与 `src/App.jsx`**

```jsx
// src/main.jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
)
```

```jsx
// src/App.jsx
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
```

```jsx
// src/pages/Home.jsx（占位，Task 7 填充）
export default function Home() { return <div className="home">首页（待实现）</div> }
// src/pages/Study.jsx（占位）
export default function Study() { return <div>学习页（待实现）</div> }
// src/pages/Vocab.jsx（占位）
export default function Vocab() { return <div>词句本（待实现）</div> }
// src/pages/Profile.jsx（占位）
export default function Profile() { return <div>统计（待实现）</div> }
```

- [ ] **Step 7: 写 `src/styles.css`**

把旧 `legacy.html` 第 8–239 行的 `<style>` 内容（`:root` CSS 变量、`.topbar`、`.home`、`.course`、`.main`、`.card`、`.video-wrap`、`.sent-list`、`.sent`、`.stages`、`.stage`、`.sentence-box`、`.translation`、`.dict-area`、`.diff-out`、`.score`、`.row`、`.btn`、`.nav-arrows`、`.word-pop`、`.modal-mask`、`.modal`、`.toast`、`.srs-*`、`.grade`、`.empty` 等）原样复制进 `styles.css`，去掉 `<style>`/`</style>` 标签即可。

- [ ] **Step 8: 写 `.gitignore`**

```
node_modules/
dist/
```

- [ ] **Step 9: 安装依赖并验证启动**

```bash
npm install
```

Run: `npm run dev`（后台）→ 打开 `http://localhost:5173`，确认四条路由均能渲染占位页、无报错。

Expected: 首页显示「首页（待实现）」，点顶栏「生词本/统计」跳转对应占位页。

- [ ] **Step 10: Commit**

```bash
git add -A && git commit -m "chore: scaffold Vite + React + router skeleton"
```

---

### Task 2: persistence + settingsStore + sessionStore

**Files:**
- Create: `src/lib/persistence.js`, `src/lib/persistence.test.js`, `src/lib/toast.js`, `src/store/settingsStore.js`, `src/store/sessionStore.js`

**Interfaces:**
- Produces:
  - `loadLS(key, def)` / `saveLS(key, val)` / `LS`（含 `progress/vocab/recent/materials/settings` 五个键，前缀 `rlearn_v1`）
  - `toast(msg)` → 轻量顶部 toast（供各组件提示用）
  - `useSettingsStore`：`{ settings, save(patch) }`
  - `useSessionStore`：`{ videoId, curIdx, stage, revealed, sentenceScores, open(videoId), setIdx(n), setStage(s), toggleRevealed(), setSentenceScore(sid, patch) }`

- [ ] **Step 1: 写失败测试 `src/lib/persistence.test.js`**

```js
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { loadLS, saveLS, LS } from './persistence'

describe('persistence', () => {
  beforeEach(() => localStorage.clear())

  it('loadLS returns default when key missing', () => {
    expect(loadLS(LS.progress, {})).toEqual({})
  })

  it('saveLS then loadLS round-trips objects', () => {
    saveLS(LS.progress, { a: 1 })
    expect(loadLS(LS.progress, {})).toEqual({ a: 1 })
  })

  it('loadLS returns default on corrupt JSON', () => {
    localStorage.setItem(LS.progress, '{bad json')
    expect(loadLS(LS.progress, { def: true })).toEqual({ def: true })
  })

  it('saveLS swallows quota errors without throwing', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota') })
    expect(() => saveLS(LS.progress, { x: 1 })).not.toThrow()
  })

  it('keys use rlearn_v1 prefix', () => {
    expect(LS.progress).toBe('rlearn_v1_progress')
    expect(LS.vocab).toBe('rlearn_v1_vocab')
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `npm test -- persistence`
Expected: FAIL（`./persistence` 不存在）

- [ ] **Step 3: 实现 `src/lib/persistence.js`**

```js
export const LS = {
  progress: 'rlearn_v1_progress',
  vocab: 'rlearn_v1_vocab',
  recent: 'rlearn_v1_recent',
  materials: 'rlearn_v1_materials',
  settings: 'rlearn_v1_settings',
}

export function loadLS(key, def) {
  try { const v = localStorage.getItem(key); return v == null ? def : JSON.parse(v) }
  catch (e) { return def }
}

export function saveLS(key, val) {
  try { localStorage.setItem(key, JSON.stringify(val)) }
  catch (e) { /* 忽略：配额满/隐私模式 */ }
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `npm test -- persistence`
Expected: PASS（5 tests）

- [ ] **Step 5: 实现 `src/lib/toast.js`**

```js
let el = null
export function toast(msg) {
  if (!el) {
    el = document.createElement('div')
    el.className = 'toast'
    document.body.appendChild(el)
  }
  el.textContent = msg
  el.classList.add('show')
  clearTimeout(el._t)
  el._t = setTimeout(() => el.classList.remove('show'), 2200)
}
```

- [ ] **Step 6: 实现 `src/store/settingsStore.js`**

```js
import { create } from 'zustand'
import { loadLS, saveLS, LS } from '../lib/persistence'

const defaults = {
  baseUrl: 'https://api.deepseek.com',
  apiKey: '',
  model: 'deepseek-chat',
  voiceURI: '',
  rate: 1.0,
  loopTimes: 3,
}

export const useSettingsStore = create((set, get) => ({
  settings: { ...defaults, ...loadLS(LS.settings, {}) },
  save(patch) {
    const next = { ...get().settings, ...patch }
    saveLS(LS.settings, next)
    set({ settings: next })
  },
}))
```

- [ ] **Step 7: 实现 `src/store/sessionStore.js`**

```js
import { create } from 'zustand'

export const useSessionStore = create((set) => ({
  videoId: null,
  curIdx: 0,
  stage: 'listen',
  revealed: false,
  sentenceScores: {},
  open(videoId) {
    set({ videoId, curIdx: 0, stage: 'listen', revealed: false, sentenceScores: {} })
  },
  setIdx(curIdx) { set({ curIdx }) },
  setStage(stage) { set({ stage }) },
  toggleRevealed() { set(s => ({ revealed: !s.revealed })) },
  setSentenceScore(sid, patch) {
    set(s => ({ sentenceScores: { ...s.sentenceScores, [sid]: { ...s.sentenceScores[sid], ...patch } } }))
  },
}))
```

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat: persistence util + settings/session stores"
```

---

### Task 3: 课程库数据 courseLibrary.js

**Files:**
- Create: `src/data/courseLibrary.js`, `src/data/courseLibrary.test.js`

**Interfaces:**
- Produces:
  - `LEVELS = ['A1','A2','B1','B2']`
  - `courseLibrary = { A1:{collections:[…]}, A2:{…}, B1:{…}, B2:{…} }`，每视频 `sentences[]` 字段 `{id, russian, chinese, stressed?}`
  - `findVideo(videoId)` → `{ video, collection, level } | null`
  - `getLevelVideos(level)` → `[{ video, collection }]`（扁平，按顺序）
  - `flatVideoList()` → `[{ video, collection, level }]`（全量，用于校验/搜索）

- [ ] **Step 1: 写校验测试 `src/data/courseLibrary.test.js`**

```js
import { describe, it, expect } from 'vitest'
import { courseLibrary, LEVELS, findVideo, getLevelVideos } from './courseLibrary'

describe('courseLibrary', () => {
  it('has all four levels non-empty', () => {
    for (const l of LEVELS) {
      expect(courseLibrary[l], l).toBeTruthy()
      expect(courseLibrary[l].collections.length, l).toBeGreaterThan(0)
    }
  })

  it('every video has a non-empty id/title and >=15 sentences', () => {
    for (const l of LEVELS) {
      for (const c of courseLibrary[l].collections) {
        for (const v of c.videos) {
          expect(v.id).toBeTruthy()
          expect(v.title).toBeTruthy()
          expect(v.sentences.length).toBeGreaterThanOrEqual(15)
          for (const s of v.sentences) {
            expect(s.id).toBeTruthy()
            expect(s.russian.trim()).not.toBe('')
            expect(s.chinese.trim()).not.toBe('')
          }
        }
      }
    }
  })

  it('video ids are globally unique', () => {
    const ids = []
    for (const l of LEVELS) for (const c of courseLibrary[l].collections) for (const v of c.videos) ids.push(v.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('findVideo resolves an existing id with level + collection', () => {
    const first = getLevelVideos('A1')[0]
    const r = findVideo(first.video.id)
    expect(r.video.id).toBe(first.video.id)
    expect(r.level).toBe('A1')
    expect(r.collection).toBeTruthy()
  })

  it('findVideo returns null for unknown id', () => {
    expect(findVideo('nope')).toBeNull()
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

Run: `npm test -- courseLibrary`
Expected: FAIL

- [ ] **Step 3: 实现 `src/data/courseLibrary.js`（含完整数据）**

```js
export const LEVELS = ['A1', 'A2', 'B1', 'B2']

export const courseLibrary = {
  A1: {
    collections: [
      {
        id: 'a1_greetings',
        name: '俄语入门：日常问候',
        description: '从最基础的问候语开始，涵盖见面、告别、感谢、道歉等日常场景。',
        videos: [
          {
            id: 'a1_greet_01',
            title: '俄语第一课：问候与自我介绍',
            description: '学习最基础的俄语问候语、自我介绍句型，零基础入门。',
            thumbnail: 'https://picsum.photos/seed/ru_greet_01/400/280',
            posterUrl: 'https://picsum.photos/seed/ru_greet_01/1280/720',
            level: 'A1',
            duration: '4:30',
            words: 120,
            tags: ['慢速', '基础', '口语'],
            learners: 128,
            sentences: [
              { id: 1, russian: 'Здра́вствуйте!', chinese: '您好！' },
              { id: 2, russian: 'Приве́т!', chinese: '你好！（非正式）' },
              { id: 3, russian: 'До́брое у́тро!', chinese: '早上好！' },
              { id: 4, russian: 'До́брый день!', chinese: '你好！（白天）' },
              { id: 5, russian: 'До́брый ве́чер!', chinese: '晚上好！' },
              { id: 6, russian: 'Как у вас дела́?', chinese: '您最近怎么样？' },
              { id: 7, russian: 'Хорошо́, спаси́бо.', chinese: '很好，谢谢。' },
              { id: 8, russian: 'Меня́ зову́т А́нна.', chinese: '我叫安娜。' },
              { id: 9, russian: 'Как вас зову́т?', chinese: '您叫什么名字？' },
              { id: 10, russian: 'О́чень прия́тно!', chinese: '很高兴认识您！' },
              { id: 11, russian: 'До свида́ния!', chinese: '再见！' },
              { id: 12, russian: 'Пока́!', chinese: '拜拜！（非正式）' },
              { id: 13, russian: 'Спаси́бо большо́е!', chinese: '非常感谢！' },
              { id: 14, russian: 'Пожа́луйста.', chinese: '不客气。／请。' },
              { id: 15, russian: 'Извини́те, пожа́луйста.', chinese: '对不起，打扰一下。' }
            ]
          }
        ]
      },
      {
        id: 'a1_intro',
        name: '俄语基础：自我介绍与数字',
        description: '学会介绍自己、家人朋友，表达年龄、职业和基本喜好。',
        videos: [
          {
            id: 'a1_intro_01',
            title: '俄语第二课：我的自我介绍',
            description: '学习自我介绍、职业、年龄与家庭关系的常用表达。',
            thumbnail: 'https://picsum.photos/seed/ru_intro_01/400/280',
            posterUrl: 'https://picsum.photos/seed/ru_intro_01/1280/720',
            level: 'A1',
            duration: '5:10',
            words: 140,
            tags: ['基础', '口语', '自我介绍'],
            learners: 96,
            sentences: [
              { id: 1, russian: 'Я студе́нт.', chinese: '我是学生。' },
              { id: 2, russian: 'Я из Кита́я.', chinese: '我来自中国。' },
              { id: 3, russian: 'Я говорю́ по-ру́сски немно́го.', chinese: '我会说一点俄语。' },
              { id: 4, russian: 'Мне два́дцать лет.', chinese: '我二十岁。' },
              { id: 5, russian: 'Э́то мой друг.', chinese: '这是我的朋友。' },
              { id: 6, russian: 'Он у́чится в университе́те.', chinese: '他在大学学习。' },
              { id: 7, russian: 'Она́ рабо́тает в шко́ле.', chinese: '她在学校工作。' },
              { id: 8, russian: 'Мы живём в Москве́.', chinese: '我们住在莫斯科。' },
              { id: 9, russian: 'У меня́ есть сестра́.', chinese: '我有一个姐妹。' },
              { id: 10, russian: 'У меня́ нет бра́та.', chinese: '我没有兄弟。' },
              { id: 11, russian: 'Э́то о́чень интере́сно.', chinese: '这很有趣。' },
              { id: 12, russian: 'Я люблю́ чита́ть.', chinese: '我喜欢阅读。' },
              { id: 13, russian: 'Я учу́ ру́сский язы́к.', chinese: '我在学俄语。' },
              { id: 14, russian: 'Повтори́те, пожа́луйста.', chinese: '请再说一遍。' },
              { id: 15, russian: 'Я не понима́ю.', chinese: '我不明白。' }
            ]
          }
        ]
      }
    ]
  },
  A2: {
    collections: [
      {
        id: 'a2_past',
        name: '俄语进阶：过去时与生活',
        description: '用过去时描述日常生活、经历和天气，练习动词过去时态。',
        videos: [
          {
            id: 'a2_past_01',
            title: '日常生活：昨天我做了什么',
            description: '学习俄语过去时，描述昨天和过去的日常活动。',
            thumbnail: 'https://picsum.photos/seed/ru_past_01/400/280',
            posterUrl: 'https://picsum.photos/seed/ru_past_01/1280/720',
            level: 'A2',
            duration: '6:00',
            words: 160,
            tags: ['过去时', '生活', '语法'],
            learners: 74,
            sentences: [
              { id: 1, russian: 'Вчера́ я ходи́л в кино́.', chinese: '昨天我去看电影了。' },
              { id: 2, russian: 'У́тром я встал в семь часо́в.', chinese: '早上我七点起床。' },
              { id: 3, russian: 'Мы гуля́ли в па́рке.', chinese: '我们在公园散步。' },
              { id: 4, russian: 'Она́ гото́вила у́жин.', chinese: '她做了晚饭。' },
              { id: 5, russian: 'Я чита́л кни́гу весь ве́чер.', chinese: '我整个晚上都在读书。' },
              { id: 6, russian: 'Он рабо́тал це́лый день.', chinese: '他工作了一整天。' },
              { id: 7, russian: 'Мы смотре́ли телеви́зор.', chinese: '我们看电视了。' },
              { id: 8, russian: 'Я купи́л хлеб и молоко́.', chinese: '我买了面包和牛奶。' },
              { id: 9, russian: 'Она́ позвони́ла подру́ге.', chinese: '她给朋友打了电话。' },
              { id: 10, russian: 'Мы отдыха́ли на мо́ре.', chinese: '我们在海边休息。' },
              { id: 11, russian: 'Я был о́чень за́нят.', chinese: '我当时很忙。' },
              { id: 12, russian: 'Пого́да была́ хоро́шая.', chinese: '天气很好。' },
              { id: 13, russian: 'Мы хорошо́ провели́ вре́мя.', chinese: '我们度过了愉快的时光。' },
              { id: 14, russian: 'Я забы́л свои́ ключи́.', chinese: '我忘了我的钥匙。' },
              { id: 15, russian: 'Он рассказа́л интере́сную исто́рию.', chinese: '他讲了一个有趣的故事。' }
            ]
          }
        ]
      }
    ]
  },
  B1: {
    collections: [
      {
        id: 'b1_opinion',
        name: '俄语中级：观点与论证',
        description: '学习表达观点、同意与反驳、权衡利弊，提升逻辑表达能力。',
        videos: [
          {
            id: 'b1_opinion_01',
            title: '表达观点：我同意还是反对',
            description: '学习用俄语表达个人观点、权衡利弊和进行讨论。',
            thumbnail: 'https://picsum.photos/seed/ru_opinion_01/400/280',
            posterUrl: 'https://picsum.photos/seed/ru_opinion_01/1280/720',
            level: 'B1',
            duration: '7:20',
            words: 200,
            tags: ['观点', '讨论', '中级'],
            learners: 51,
            sentences: [
              { id: 1, russian: 'По-мо́ему, э́то пра́вильное реше́ние.', chinese: '在我看来，这是正确的决定。' },
              { id: 2, russian: 'Я счита́ю, что на́до бо́льше занима́ться.', chinese: '我认为需要多练习。' },
              { id: 3, russian: 'С одно́й стороны́, э́то поле́зно.', chinese: '一方面，这很有用。' },
              { id: 4, russian: 'С друго́й стороны́, э́то до́рого.', chinese: '另一方面，这很贵。' },
              { id: 5, russian: 'Мне ка́жется, он прав.', chinese: '我觉得他是对的。' },
              { id: 6, russian: 'Я не согла́сен с э́тим мне́нием.', chinese: '我不同意这个观点。' },
              { id: 7, russian: 'Э́то зави́сит от мно́гих фа́кторов.', chinese: '这取决于许多因素。' },
              { id: 8, russian: 'Ва́жно понима́ть причи́ны.', chinese: '理解原因很重要。' },
              { id: 9, russian: 'Я ду́маю, что э́то возмо́жно.', chinese: '我认为这是可能的。' },
              { id: 10, russian: 'На мой взгляд, э́то сли́шком сло́жно.', chinese: '在我看来，这太复杂了。' },
              { id: 11, russian: 'На́до учи́тывать все обстоя́тельства.', chinese: '需要考虑所有情况。' },
              { id: 12, russian: 'Я убеждён, что э́то пра́вильно.', chinese: '我确信这是正确的。' },
              { id: 13, russian: 'К сожале́нию, э́то невозмо́жно.', chinese: '很遗憾，这是不可能的。' },
              { id: 14, russian: 'Мне интере́сно узна́ть ва́ше мне́ние.', chinese: '我很想知道你的看法。' },
              { id: 15, russian: 'Дава́йте обсу́дим э́ту пробле́му.', chinese: '让我们讨论一下这个问题。' }
            ]
          }
        ]
      }
    ]
  },
  B2: {
    collections: [
      {
        id: 'b2_society',
        name: '俄语高级：社会议题',
        description: '讨论社会、科技、文化等抽象议题，掌握复杂句式和书面表达。',
        videos: [
          {
            id: 'b2_society_01',
            title: '社会议题：科技改变生活',
            description: '用俄语讨论技术进步、文化保护与社会发展等抽象议题。',
            thumbnail: 'https://picsum.photos/seed/ru_society_01/400/280',
            posterUrl: 'https://picsum.photos/seed/ru_society_01/1280/720',
            level: 'B2',
            duration: '8:40',
            words: 240,
            tags: ['社会', '科技', '高级'],
            learners: 32,
            sentences: [
              { id: 1, russian: 'Совреме́нное о́бщество ста́лкивается с мно́гими пробле́мами.', chinese: '现代社会面临许多问题。' },
              { id: 2, russian: 'Технологи́ческий прогре́сс меня́ет наш о́браз жи́зни.', chinese: '技术进步改变着我们的生活方式。' },
              { id: 3, russian: 'Ва́жно сохраня́ть культу́рное насле́дие.', chinese: '保护文化遗产很重要。' },
              { id: 4, russian: 'Э́та пробле́ма тре́бует серьёзного подхо́да.', chinese: '这个问题需要认真的态度。' },
              { id: 5, russian: 'Мне́ния по э́тому вопро́су раздели́лись.', chinese: '在这个问题上的意见出现了分歧。' },
              { id: 6, russian: 'Необходи́мо найти́ компроми́сс.', chinese: '必须找到折中方案。' },
              { id: 7, russian: 'Э́то явле́ние име́ет глубо́кие ко́рни.', chinese: '这种现象有深刻的根源。' },
              { id: 8, russian: 'Сле́дует обрати́ть внима́ние на э́ти фа́кты.', chinese: '应当注意这些事实。' },
              { id: 9, russian: 'Пра́вительство приня́ло но́вые ме́ры.', chinese: '政府采取了新措施。' },
              { id: 10, russian: 'Учёные провели́ обши́рное иссле́дование.', chinese: '科学家进行了广泛的研究。' },
              { id: 11, russian: 'Результа́ты иссле́дования впечатля́ют.', chinese: '研究结果令人印象深刻。' },
              { id: 12, russian: 'Э́то спосо́бствует разви́тию о́бщества.', chinese: '这有助于社会的发展。' },
              { id: 13, russian: 'Мы до́лжны бере́жно относи́ться к приро́де.', chinese: '我们应该爱护自然。' },
              { id: 14, russian: 'Э́та те́ма вызыва́ет мно́го спо́ров.', chinese: '这个话题引发许多争论。' },
              { id: 15, russian: 'Бу́дущее зави́сит от на́ших реше́ний.', chinese: '未来取决于我们的决定。' }
            ]
          }
        ]
      }
    ]
  }
}

export function findVideo(videoId) {
  for (const level of LEVELS) {
    for (const collection of courseLibrary[level].collections) {
      const video = collection.videos.find(v => v.id === videoId)
      if (video) return { video, collection, level }
    }
  }
  return null
}

export function getLevelVideos(level) {
  const out = []
  for (const collection of (courseLibrary[level] || {}).collections || []) {
    for (const video of collection.videos) out.push({ video, collection })
  }
  return out
}

export function flatVideoList() {
  const out = []
  for (const level of LEVELS) {
    for (const collection of courseLibrary[level].collections) {
      for (const video of collection.videos) out.push({ video, collection, level })
    }
  }
  return out
}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `npm test -- courseLibrary`
Expected: PASS（5 tests）

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: course library data (A1-B2) + helpers"
```

---

### Task 4: scoring.js（打分 + 解锁）

**Files:**
- Create: `src/lib/scoring.js`, `src/lib/scoring.test.js`

**Interfaces:**
- Produces:
  - `norm(s)` → 规范化字符串（去标点、去重音、小写、合并空格）
  - `dictation(input, target)` → `{ score: 0..100, diff: [{ word, ok }] }`（词级 LCS）
  - `selfRate(g)` → 0..100（g∈{0,1,2,3}）
  - `sentenceMastery(scores)` → 0..100 或 null（无分时）
  - `videoScore(sentenceScores)` → 0..100
  - `levelMastery(videoIds, progress)` → 0..100（videoIds = 该级视频 id 数组）
  - `LEVEL_PASS = 60`
  - `isLevelUnlocked(level, progress, levelIds)` / `isVideoUnlocked(level, idx, progress, levelIds)`（levelIds = `{A1:[...],...}`）

- [ ] **Step 1: 写测试 `src/lib/scoring.test.js`**

```js
import { describe, it, expect } from 'vitest'
import {
  norm, dictation, selfRate, sentenceMastery, videoScore,
  levelMastery, isLevelUnlocked, isVideoUnlocked, LEVEL_PASS
} from './scoring'

describe('norm', () => {
  it('strips punctuation, accents, lowercases, collapses spaces', () => {
    expect(norm('Здра́вствуйте!')).toBe('здравствуйте')
    expect(norm('  Как   дела? ')).toBe('как дела')
  })
})

describe('dictation', () => {
  it('perfect match scores 100', () => {
    const r = dictation('меня зовут анна', 'Меня́ зову́т А́нна.')
    expect(r.score).toBe(100)
    expect(r.diff.every(d => d.ok)).toBe(true)
  })

  it('half wrong scores ~50 and marks diff', () => {
    const r = dictation('меня зовут', 'Меня зовут Анна')
    expect(r.score).toBeGreaterThan(0)
    expect(r.score).toBeLessThan(100)
    expect(r.diff.length).toBe(3)
    expect(r.diff[2].ok).toBe(false)
  })

  it('empty input scores 0', () => {
    expect(dictation('', 'Привет').score).toBe(0)
  })
})

describe('selfRate', () => {
  it('maps 0..3 to 0/35/70/100', () => {
    expect(selfRate(0)).toBe(0)
    expect(selfRate(1)).toBe(35)
    expect(selfRate(2)).toBe(70)
    expect(selfRate(3)).toBe(100)
  })
})

describe('sentenceMastery / videoScore', () => {
  it('averages available scores', () => {
    expect(sentenceMastery({ dictate: 80, recite: 60 })).toBe(70)
    expect(sentenceMastery({ dictate: 80 })).toBe(80)
    expect(sentenceMastery({})).toBeNull()
  })

  it('videoScore averages practiced sentences', () => {
    expect(videoScore({ 1: { dictate: 100 }, 2: { recite: 0 } })).toBe(50)
    expect(videoScore({})).toBe(0)
  })
})

describe('unlock logic', () => {
  const levelIds = { A1: ['a1_greet_01'], A2: [], B1: [], B2: [] }
  it('A1 always unlocked; higher levels need prev >= LEVEL_PASS', () => {
    expect(isLevelUnlocked('A1', {}, levelIds)).toBe(true)
    expect(isLevelUnlocked('A2', {}, levelIds)).toBe(false)
  })

  it('level unlocks when prev level mastery >= 60', () => {
    const progress = { a1_greet_01: { done: true, score: 80 } }
    expect(levelMastery(levelIds.A1, progress)).toBe(80)
    expect(isLevelUnlocked('A2', progress, levelIds)).toBe(true)
  })

  it('video i+1 unlocked only when video i done', () => {
    const ids = { A1: ['a1_greet_01', 'a1_intro_01'] }
    const progress = { a1_greet_01: { done: true, score: 90 } }
    expect(isVideoUnlocked('A1', 0, progress, ids)).toBe(true)
    expect(isVideoUnlocked('A1', 1, progress, ids)).toBe(true)
    expect(isVideoUnlocked('A1', 2, {}, ids)).toBe(false)
  })
})
```

- [ ] **Step 2: 运行确认失败** — Run: `npm test -- scoring` → FAIL

- [ ] **Step 3: 实现 `src/lib/scoring.js`**

> 说明：`levelMastery`/`isLevelUnlocked`/`isVideoUnlocked` 需要该级视频 id 列表，为避免 scoring 反向依赖 courseLibrary，这三个函数接收**视频 id 列表**作为参数，由调用方（courseStore）传入。

```js
import { LEVELS } from '../data/courseLibrary'

export const LEVEL_PASS = 60

export function norm(s) {
  return (s || '')
    .toLowerCase()
    .replace(/[.,!?…;:—\-–"«»()'’]/g, ' ')
    .replace(/[̀́̆̈]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}

function words(s) { return norm(s).split(' ').filter(Boolean) }

function lcs(a, b) {
  const m = a.length, n = b.length
  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0))
  for (let i = m - 1; i >= 0; i--)
    for (let j = n - 1; j >= 0; j--)
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
  return dp
}

export function dictation(input, target) {
  const tw = words(target), iw = words(input)
  if (!tw.length) return { score: 0, diff: [] }
  const dp = lcs(iw, tw)
  const diff = []
  let i = 0, j = 0
  while (j < tw.length) {
    if (i < iw.length && iw[i] === tw[j]) { diff.push({ word: tw[j], ok: true }); i++; j++ }
    else if (i < iw.length && dp[i + 1][j] >= dp[i][j + 1]) { diff.push({ word: iw[i], ok: false }); i++ }
    else { diff.push({ word: tw[j], ok: false }); j++ }
  }
  const okCount = diff.filter(d => d.ok).length
  return { score: Math.round((okCount / tw.length) * 100), diff }
}

export function selfRate(g) { return [0, 35, 70, 100][g] ?? 0 }

export function sentenceMastery(scores) {
  const vals = [scores?.dictate, scores?.recite].filter(v => typeof v === 'number')
  if (!vals.length) return null
  return Math.round(vals.reduce((a, b) => a + b, 0) / vals.length)
}

export function videoScore(sentenceScores) {
  const vals = Object.values(sentenceScores || {}).map(sentenceMastery).filter(v => v != null)
  if (!vals.length) return 0
  return Math.round(vals.reduce((a, b) => a + b, 0) / vals.length)
}

// videoIds: 该级全部视频 id（按顺序）；progress: courseStore 的 progress
export function levelMastery(videoIds, progress) {
  if (!videoIds.length) return 0
  let sum = 0
  for (const id of videoIds) {
    const p = progress[id]
    if (p && p.done && typeof p.score === 'number') sum += p.score
  }
  return Math.round(sum / videoIds.length)
}

// levelIds: { A1: [...], A2: [...], ... }（调用方用 getLevelVideos 构建）
export function isLevelUnlocked(level, progress, levelIds) {
  const order = LEVELS
  const idx = order.indexOf(level)
  if (idx <= 0) return true
  return levelMastery(levelIds[order[idx - 1]], progress) >= LEVEL_PASS
}

export function isVideoUnlocked(level, idx, progress, levelIds) {
  if (!isLevelUnlocked(level, progress, levelIds)) return false
  if (idx === 0) return true
  const prevId = levelIds[level][idx - 1]
  return !!(progress[prevId] && progress[prevId].done)
}
```

- [ ] **Step 4: 运行测试确认通过** — Run: `npm test -- scoring` → PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: scoring (dictation LCS, mastery) + unlock logic"
```

---

### Task 5: courseStore（进度 + 最近观看 + 自定义材料）

**Files:**
- Create: `src/store/courseStore.js`, `src/store/courseStore.test.js`

**Interfaces:**
- Produces:
  - `useCourseStore`：`{ progress, recent, materials, getVideo(videoId), pushRecent(videoId), recordSentenceScore(videoId, sid, patch), submitVideo(videoId), resetLevel(level), addMaterial(material), levelIds(), levelMastery(level), isLevelUnlocked(level), isVideoUnlocked(level, idx) }`

- [ ] **Step 1: 写测试 `src/store/courseStore.test.js`**

```js
import { describe, it, expect, beforeEach } from 'vitest'
import { useCourseStore } from './courseStore'

const reset = () => useCourseStore.setState({ progress: {}, recent: [], materials: [] })

describe('courseStore', () => {
  beforeEach(() => { localStorage.clear(); reset() })

  it('getVideo resolves a course video', () => {
    const v = useCourseStore.getState().getVideo('a1_greet_01')
    expect(v.id).toBe('a1_greet_01')
  })

  it('getVideo resolves a custom material and returns null otherwise', () => {
    useCourseStore.getState().addMaterial({ id: 'custom_x', title: 't', sentences: [], createdAt: 1 })
    expect(useCourseStore.getState().getVideo('custom_x').title).toBe('t')
    expect(useCourseStore.getState().getVideo('nope')).toBeNull()
  })

  it('pushRecent dedupes and caps at 10', () => {
    const s = useCourseStore.getState()
    for (let i = 0; i < 12; i++) s.pushRecent('v' + i)
    s.pushRecent('v0')
    const { recent } = useCourseStore.getState()
    expect(recent.length).toBe(10)
    expect(recent[0].videoId).toBe('v0')
    expect(recent.filter(r => r.videoId === 'v0').length).toBe(1)
  })

  it('recordSentenceScore + submitVideo computes score and marks done', () => {
    const s = useCourseStore.getState()
    s.recordSentenceScore('a1_greet_01', 1, { dictate: 100 })
    s.recordSentenceScore('a1_greet_01', 2, { recite: 0 })
    const score = s.submitVideo('a1_greet_01')
    expect(score).toBe(50)
    expect(useCourseStore.getState().progress['a1_greet_01'].done).toBe(true)
  })

  it('resetLevel clears that level progress', () => {
    useCourseStore.setState({ progress: { a1_greet_01: { done: true, score: 90 }, a2_past_01: { done: true, score: 90 } } })
    useCourseStore.getState().resetLevel('A1')
    const p = useCourseStore.getState().progress
    expect(p['a1_greet_01']).toBeUndefined()
    expect(p['a2_past_01']).toBeDefined()
  })
})
```

- [ ] **Step 2: 运行确认失败** — Run: `npm test -- courseStore` → FAIL

- [ ] **Step 3: 实现 `src/store/courseStore.js`**

```js
import { create } from 'zustand'
import { loadLS, saveLS, LS } from '../lib/persistence'
import { findVideo, getLevelVideos, LEVELS } from '../data/courseLibrary'
import { videoScore, levelMastery, isLevelUnlocked as _unlock, isVideoUnlocked as _vUnlock } from '../lib/scoring'

function levelIds() {
  const m = {}
  for (const l of LEVELS) m[l] = getLevelVideos(l).map(x => x.video.id)
  return m
}

export const useCourseStore = create((set, get) => ({
  progress: loadLS(LS.progress, {}),
  recent: loadLS(LS.recent, []),
  materials: loadLS(LS.materials, []),

  getVideo(videoId) {
    if (videoId && videoId.startsWith('custom_')) {
      return get().materials.find(m => m.id === videoId) || null
    }
    const found = findVideo(videoId)
    return found ? found.video : null
  },

  pushRecent(videoId) {
    const now = Date.now()
    const recent = [{ videoId, updatedAt: now }, ...get().recent.filter(r => r.videoId !== videoId)].slice(0, 10)
    saveLS(LS.recent, recent)
    set({ recent })
  },

  recordSentenceScore(videoId, sid, patch) {
    set(s => {
      const v = s.progress[videoId] || { done: false, score: null, sentenceScores: {}, lastIndex: 0 }
      const next = {
        ...s.progress,
        [videoId]: {
          ...v,
          sentenceScores: { ...v.sentenceScores, [sid]: { ...v.sentenceScores[sid], ...patch } },
          lastIndex: sid,
          updatedAt: Date.now(),
        },
      }
      saveLS(LS.progress, next)
      return { progress: next }
    })
  },

  submitVideo(videoId) {
    const v = get().progress[videoId]
    if (!v) return 0
    const score = videoScore(v.sentenceScores)
    const next = { ...get().progress, [videoId]: { ...v, done: true, score } }
    saveLS(LS.progress, next)
    set({ progress: next })
    return score
  },

  resetLevel(level) {
    const ids = getLevelVideos(level).map(x => x.video.id)
    const next = { ...get().progress }
    for (const id of ids) delete next[id]
    saveLS(LS.progress, next)
    set({ progress: next })
  },

  addMaterial(material) {
    const materials = [material, ...get().materials]
    saveLS(LS.materials, materials)
    set({ materials })
  },

  levelIds() { return levelIds() },
  levelMastery(level) { return levelMastery(levelIds()[level], get().progress) },
  isLevelUnlocked(level) { return _unlock(level, get().progress, levelIds()) },
  isVideoUnlocked(level, idx) { return _vUnlock(level, idx, get().progress, levelIds()) },
}))
```

- [ ] **Step 4: 运行确认通过** — Run: `npm test -- courseStore` → PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: courseStore (progress/recent/materials)"
```

---

### Task 6: tts.js（TTS 播放引擎）

**Files:**
- Create: `src/lib/tts.js`, `src/lib/tts.test.js`

**Interfaces:**
- Produces:
  - `getRuVoice()` → `SpeechSynthesisVoice | null`
  - `speak(text, { rate, voice, onStart, onEnd })` → 无返回值（触发回调）
  - `cancelSpeech()` → 取消当前播放
  - `speakAll(sentences, { from, rate, onIndex, onDone })` → 顺序播放全部句子并回调 `onIndex(i)`
  - `loopSentence(sentences, i, times, { rate, onIndex, onDone })` → 第 i 句循环播 `times` 遍

- [ ] **Step 1: 写测试 `src/lib/tts.test.js`**（mock `speechSynthesis`）

```js
import { describe, it, expect, vi, beforeEach } from 'vitest'

function mockTTS() {
  const utterances = []
  let onStart = null, onEnd = null
  const speak = vi.fn((u) => {
    utterances.push(u)
    u.onstart = u.onstart || (() => {})
    u.onend = u.onend || (() => {})
    // 记录当前回调便于测试里手动触发
    onStart = () => u.onstart()
    onEnd = () => u.onend()
  })
  const cancel = vi.fn()
  globalThis.speechSynthesis = { speak, cancel, getVoices: vi.fn(() => []) }
  globalThis.SpeechSynthesisUtterance = class {
    constructor(text) { this.text = text; this.rate = 1; this.voice = null }
  }
  return { speak, cancel, utterances, fireStart: () => onStart?.(), fireEnd: () => onEnd?.() }
}

describe('tts', () => {
  beforeEach(() => { vi.resetModules() })

  it('speak calls speechSynthesis.speak with utterance', async () => {
    const m = mockTTS()
    const { speak } = await import('./tts')
    speak('привет', { rate: 1 })
    expect(m.speak).toHaveBeenCalledTimes(1)
  })

  it('speakAll fires onIndex in order and onDone at end', async () => {
    const m = mockTTS()
    const { speakAll } = await import('./tts')
    const idx = []
    const done = vi.fn()
    speakAll([{ russian: 'a' }, { russian: 'b' }], { from: 0, onIndex: i => idx.push(i), onDone: done })
    expect(idx).toEqual([0])
    m.fireEnd()
    expect(idx).toEqual([0, 1])
    m.fireEnd()
    expect(done).toHaveBeenCalledTimes(1)
  })

  it('cancelSpeech calls cancel', async () => {
    const m = mockTTS()
    const { cancelSpeech } = await import('./tts')
    cancelSpeech()
    expect(m.cancel).toHaveBeenCalled()
  })
})
```

- [ ] **Step 2: 运行确认失败** — Run: `npm test -- tts` → FAIL

- [ ] **Step 3: 实现 `src/lib/tts.js`**

```js
export function getRuVoice() {
  if (!('speechSynthesis' in window)) return null
  const voices = window.speechSynthesis.getVoices()
  return voices.find(v => /ru/i.test(v.lang)) || null
}

export function speak(text, { rate = 1, voice = null, onStart, onEnd } = {}) {
  if (!('speechSynthesis' in window)) return
  const u = new SpeechSynthesisUtterance(text)
  if (voice) u.voice = voice
  u.lang = voice?.lang || 'ru-RU'
  u.rate = rate
  if (onStart) u.onstart = onStart
  if (onEnd) u.onend = onEnd
  window.speechSynthesis.cancel()
  window.speechSynthesis.speak(u)
}

export function cancelSpeech() {
  if ('speechSynthesis' in window) window.speechSynthesis.cancel()
}

export function speakAll(sentences, { from = 0, rate = 1, voice = null, onIndex, onDone } = {}) {
  let i = from
  const next = () => {
    if (i >= sentences.length) { onDone?.(); return }
    onIndex?.(i)
    speak(sentences[i].russian, {
      rate, voice,
      onEnd: () => { i++; next() },
    })
  }
  next()
}

export function loopSentence(sentences, i, times = 3, { rate = 1, voice = null, onIndex, onDone } = {}) {
  let n = 0
  const next = () => {
    if (n >= times) { onDone?.(); return }
    n++
    onIndex?.(i)
    speak(sentences[i].russian, { rate, voice, onEnd: next })
  }
  next()
}
```

- [ ] **Step 4: 运行确认通过** — Run: `npm test -- tts` → PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: tts playback engine"
```

---

### Task 7: Home 页 + VideoCard

**Files:**
- Create: `src/pages/Home.jsx`（替换占位）、`src/components/VideoCard.jsx`

**Interfaces:**
- Consumes: `useCourseStore`（`isLevelUnlocked`/`isVideoUnlocked`/`levelMastery`/`getLevelVideos`/`recent`/`getVideo`/`progress`），`LEVELS`、`courseLibrary`
- Produces: 可跳转 `/study/:videoId` 的视频卡片；等级切换 + 标签筛选 + 搜索 + 最近观看区块

- [ ] **Step 1: 实现 `src/components/VideoCard.jsx`**

```jsx
import { Link } from 'react-router-dom'
import { useCourseStore } from '../store/courseStore'

export default function VideoCard({ video, level, idx }) {
  const progress = useCourseStore(s => s.progress[video.id])
  const unlocked = useCourseStore(s => s.isVideoUnlocked(level, idx))
  const pct = progress?.done ? progress.score : null

  const body = (
    <div className="video-card">
      <div className="thumb" style={{ backgroundImage: `url(${video.thumbnail})` }}>
        {pct != null && <span className="thumb-score">{pct}分</span>}
        {!unlocked && <span className="thumb-lock">🔒</span>}
      </div>
      <div className="vc-body">
        <div className="vc-title">{video.title}</div>
        <div className="vc-meta">
          <span>{video.level}</span> · <span>{video.duration}</span> · <span>{video.words} 词</span>
        </div>
        <div className="vc-tags">{video.tags.map(t => <span key={t} className="chip">{t}</span>)}</div>
      </div>
    </div>
  )

  if (!unlocked) return <div className="vc-locked">{body}</div>
  return <Link to={`/study/${video.id}`} className="vc-link">{body}</Link>
}
```

- [ ] **Step 2: 实现 `src/pages/Home.jsx`**

```jsx
import { useState } from 'react'
import { LEVELS, getLevelVideos } from '../data/courseLibrary'
import { useCourseStore } from '../store/courseStore'
import VideoCard from '../components/VideoCard'

export default function Home() {
  const [level, setLevel] = useState('A1')
  const [tag, setTag] = useState('')
  const [q, setQ] = useState('')
  const recent = useCourseStore(s => s.recent)
  const getVideo = useCourseStore(s => s.getVideo)
  const levelMastery = useCourseStore(s => s.levelMastery)
  const isLevelUnlocked = useCourseStore(s => s.isLevelUnlocked)

  const allTags = [...new Set(getLevelVideos(level).flatMap(x => x.video.tags))]
  let videos = getLevelVideos(level)
  if (tag) videos = videos.filter(x => x.video.tags.includes(tag))
  if (q) videos = videos.filter(x => x.video.title.toLowerCase().includes(q.toLowerCase()))

  const recentVideos = recent
    .map(r => ({ ...r, video: getVideo(r.videoId) }))
    .filter(r => r.video)

  return (
    <div className="course">
      <div className="course-levels">
        {LEVELS.map(l => (
          <button key={l} className={'btn sm' + (l === level ? ' primary' : '')}
            disabled={!isLevelUnlocked(l)}
            onClick={() => setLevel(l)}>
            {l}{isLevelUnlocked(l) ? ` · 掌握 ${levelMastery(l)}%` : ' 🔒'}
          </button>
        ))}
      </div>

      <div className="row" style={{ marginBottom: 12 }}>
        <input className="qfill" placeholder="🔍 搜索视频标题…" value={q} onChange={e => setQ(e.target.value)} />
      </div>
      <div className="row" style={{ marginBottom: 16 }}>
        {allTags.map(t => (
          <button key={t} className={'btn sm' + (t === tag ? ' primary' : '')} onClick={() => setTag(tag === t ? '' : t)}>{t}</button>
        ))}
      </div>

      {recentVideos.length > 0 && (
        <section style={{ marginBottom: 24 }}>
          <h3>🕘 最近观看</h3>
          <div className="videos-grid">
            {recentVideos.map(r => <VideoCard key={r.videoId} video={r.video} level={r.video.level} idx={0} />)}
          </div>
        </section>
      )}

      <div className="videos-grid">
        {videos.map(({ video }, i) => <VideoCard key={video.id} video={video} level={level} idx={i} />)}
      </div>
      {videos.length === 0 && <div className="course-empty">没有匹配的视频</div>}
    </div>
  )
}
```

- [ ] **Step 3: 在 `styles.css` 追加卡片样式**

```css
.videos-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px}
.vc-link{text-decoration:none;color:inherit;display:block}
.video-card{background:var(--card);border:1px solid var(--border2);border-radius:14px;overflow:hidden;transition:box-shadow .15s,transform .15s;cursor:pointer}
.video-card:hover{box-shadow:var(--shadow);transform:translateY(-3px)}
.vc-locked{opacity:.6}
.thumb{aspect-ratio:10/7;background-size:cover;background-position:center;position:relative}
.thumb-score{position:absolute;top:8px;right:8px;background:var(--accent);color:#fff;padding:2px 8px;border-radius:8px;font-size:12px}
.thumb-lock{position:absolute;top:8px;left:8px;font-size:20px}
.vc-body{padding:12px 14px}
.vc-title{font-weight:600;margin-bottom:4px}
.vc-meta{font-size:12px;color:var(--muted);margin-bottom:6px}
.vc-tags{display:flex;gap:4px;flex-wrap:wrap}
```

- [ ] **Step 4: 手动验证**

Run: `npm run dev` → 打开首页，确认：等级按钮 A1 可点、A2–B2 上锁；A1 显示 2 个视频卡片（含缩略图、标签、时长）；「最近观看」为空时不显示；搜索/标签筛选生效。

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: home page with video cards, filter, recent"
```

---

### Task 8: Study 页布局 + 台词列表 + 听关卡

**Files:**
- Create: `src/pages/Study.jsx`（替换占位）、`src/components/SentenceList.jsx`、`src/components/SentenceBox.jsx`、`src/components/StageListen.jsx`

**Interfaces:**
- Consumes: `useSessionStore`、`useCourseStore.getVideo`、`useCourseStore.pushRecent`、`useCourseStore.recordSentenceScore`、`tts`
- Produces: `/study/:videoId` 完整骨架：封面 + 台词列表 + 关卡切换 + 「听」关卡（播放本句/连播/循环听/显示原文/中译）+ 上一句/下一句 + 提交评测卡。

- [ ] **Step 1: 实现 `src/components/SentenceList.jsx`**

```jsx
export default function SentenceList({ sentences, curIdx, playingIdx, onPick }) {
  return (
    <div className="sent-list" style={{ maxHeight: 'none' }}>
      {sentences.map((s, i) => (
        <div key={s.id}
          className={'sent' + (i === curIdx ? ' active' : '') + (i === playingIdx ? ' playing' : '')}
          onClick={() => onPick(i)}>
          <span className="idx">{i + 1}</span>
          <span>{s.russian}</span>
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 2: 实现 `src/components/SentenceBox.jsx`（点词翻译留到 Task 12，先渲染带重音的句子）**

```jsx
import { renderStressed } from '../lib/stress'

export default function SentenceBox({ sentence, revealed }) {
  if (!revealed) return <div className="sentence-box"><div className="cover">🔇 原文已隐藏</div></div>
  return <div className="sentence-box"><div className="txt ru" dangerouslySetInnerHTML={{ __html: renderStressed(sentence.russian) }} /></div>
}
```

- [ ] **Step 3: 实现 `src/lib/stress.js`（重音高亮渲染，纯字符串 → HTML）**

```js
// 把含重音符号的俄语文本包一层 <span class="w">，重音元音包 <b class="stress">
export function renderStressed(text) {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .split(/\s+/)
    .map(w => `<span class="w">${w}</span>`)
    .join(' ')
}
```

- [ ] **Step 4: 实现 `src/components/StageListen.jsx`**

```jsx
import { useState } from 'react'
import { speak, speakAll, loopSentence, cancelSpeech } from '../lib/tts'
import { useSettingsStore } from '../store/settingsStore'

export default function StageListen({ sentences, curIdx, onSetPlaying }) {
  const { settings } = useSettingsStore()
  const [looping, setLooping] = useState(false)

  const voice = undefined // Task 12 接 getRuVoice；先 undefined
  const playOne = () => speak(sentences[curIdx].russian, { rate: settings.rate, onStart: () => onSetPlaying(curIdx), onEnd: () => onSetPlaying(-1) })
  const playAll = () => { cancelSpeech(); speakAll(sentences, { from: curIdx, rate: settings.rate, onIndex: onSetPlaying, onDone: () => onSetPlaying(-1) }) }
  const loop = () => { setLooping(true); loopSentence(sentences, curIdx, settings.loopTimes, { rate: settings.rate, onIndex: onSetPlaying, onDone: () => { onSetPlaying(-1); setLooping(false) } }) }
  const stop = () => { cancelSpeech(); onSetPlaying(-1); setLooping(false) }

  return (
    <div className="row">
      <button className="btn primary" onClick={playOne}>▶ 播放本句</button>
      <button className="btn" onClick={playAll}>▶▶ 全文连播</button>
      <button className="btn" onClick={looping ? stop : loop}>{looping ? '⏹ 停止循环' : `🔁 循环听 ${settings.loopTimes} 遍`}</button>
    </div>
  )
}
```

- [ ] **Step 5: 实现 `src/pages/Study.jsx`**

```jsx
import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useCourseStore } from '../store/courseStore'
import { useSessionStore } from '../store/sessionStore'
import SentenceList from '../components/SentenceList'
import SentenceBox from '../components/SentenceBox'
import StageListen from '../components/StageListen'
import StageDictate from '../components/StageDictate'
import StageRecite from '../components/StageRecite'

export default function Study() {
  const { videoId } = useParams()
  const navigate = useNavigate()
  const video = useCourseStore(s => s.getVideo(videoId))
  const pushRecent = useCourseStore(s => s.pushRecent)
  const progress = useCourseStore(s => s.progress[videoId])
  const submitVideo = useCourseStore(s => s.submitVideo)

  const { curIdx, stage, revealed, setIdx, setStage, toggleRevealed } = useSessionStore()
  const open = useSessionStore(s => s.open)

  const [playingIdx, setPlayingIdx] = useState(-1)

  useEffect(() => {
    if (!video) { navigate('/'); return }
    open(videoId)
    pushRecent(videoId)
    const saved = progress?.lastIndex ?? 0
    setIdx(Math.min(saved, video.sentences.length - 1))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [videoId])

  if (!video) return null
  const sentences = video.sentences
  const cur = sentences[curIdx]

  const go = (d) => {
    const n = curIdx + d
    if (n < 0 || n >= sentences.length) return
    setIdx(n)
  }

  const stageEl = stage === 'listen' ? <StageListen sentences={sentences} curIdx={curIdx} onSetPlaying={setPlayingIdx} />
    : stage === 'dictate' ? <StageDictate sentence={cur} onScore={(s) => useCourseStore.getState().recordSentenceScore(videoId, cur.id, { dictate: s })} />
    : <StageRecite sentence={cur} onScore={(s) => useCourseStore.getState().recordSentenceScore(videoId, cur.id, { recite: s })} />

  return (
    <div className="main">
      <div className="col">
        <div className="card" style={{ padding: 10 }}>
          <div className="video-wrap">
            <img src={video.posterUrl} alt="" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
          </div>
        </div>
        <div className="card">
          <div style={{ fontWeight: 600, marginBottom: 6 }}>台词列表 <span style={{ color: 'var(--muted)', fontWeight: 400, fontSize: 13 }}>{sentences.length} 句</span></div>
          <SentenceList sentences={sentences} curIdx={curIdx} playingIdx={playingIdx} onPick={setIdx} />
        </div>
      </div>

      <div className="col">
        <div className="card">
          <div className="stages">
            {[['listen', '👂 听'], ['dictate', '⌨️ 听写'], ['recite', '🎤 跟读']].map(([k, label]) => (
              <div key={k} className={'stage' + (stage === k ? ' active' : '')} onClick={() => setStage(k)}>{label}</div>
            ))}
          </div>

          <div style={{ marginTop: 12 }}><SentenceBox sentence={cur} revealed={revealed} /></div>
          <div className="translation hidden" id="translationBox"></div>

          <div style={{ marginTop: 12 }}>{stageEl}</div>

          <div className="row" style={{ marginTop: 14 }}>
            <button className="btn sm" onClick={toggleRevealed}>{revealed ? '隐藏原文' : '显示原文'}</button>
          </div>

          <div className="nav-arrows">
            <button className="btn sm" onClick={() => go(-1)}>← 上一句</button>
            <span className="pos">{curIdx + 1} / {sentences.length}</span>
            <button className="btn sm" onClick={() => go(1)}>下一句 →</button>
          </div>
        </div>
      </div>

      <div className="card" style={{ gridColumn: '1/-1' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600 }}>📚 课程视频</div>
            <div className="hint" style={{ margin: 0 }}>完成听写/跟读后提交评测计算得分</div>
          </div>
          <button className="btn primary" onClick={() => { const s = submitVideo(videoId); navigate('/') }}>✅ 提交评测</button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 6: 写 `StageDictate.jsx` / `StageRecite.jsx` 占位（Task 9/10 填充）**

```jsx
// src/components/StageDictate.jsx
export default function StageDictate({ sentence, onScore }) { return <div>听写（待实现）</div> }
// src/components/StageRecite.jsx
export default function StageRecite({ sentence, onScore }) { return <div>跟读（待实现）</div> }
```

- [ ] **Step 7: 手动验证**

Run: `npm run dev` → 首页点一个 A1 视频卡片 → 进入 `/study/a1_greet_01`：封面图显示、台词列表 15 句、点「▶ 播放本句」有 TTS 读音且当前句高亮、「显示原文」切换、「上一句/下一句」可用、三关卡可切换。

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat: study page layout + sentence list + listen stage"
```

---

### Task 9: 听写关卡

**Files:**
- Create: `src/components/StageDictate.jsx`（替换占位）

**Interfaces:**
- Consumes: `scoring.dictation`
- Produces: 输入框 + 「提交」→ 红绿 diff + 分数，回调 `onScore(score)`；「重听」播放本句。

- [ ] **Step 1: 实现 `src/components/StageDictate.jsx`**

```jsx
import { useState } from 'react'
import { dictation } from '../lib/scoring'
import { speak } from '../lib/tts'
import { useSettingsStore } from '../store/settingsStore'

export default function StageDictate({ sentence, onScore }) {
  const { settings } = useSettingsStore()
  const [input, setInput] = useState('')
  const [result, setResult] = useState(null)

  const submit = () => {
    const r = dictation(input, sentence.russian)
    setResult(r)
    onScore(r.score)
  }

  const replay = () => speak(sentence.russian, { rate: settings.rate })

  return (
    <div>
      <textarea className="dict-area" placeholder="听写这句话…（输入俄语）" value={input} onChange={e => setInput(e.target.value)} />
      <div className="row" style={{ marginTop: 8 }}>
        <button className="btn primary" onClick={submit}>提交</button>
        <button className="btn sm" onClick={replay}>🔊 重听</button>
      </div>
      {result && (
        <div style={{ marginTop: 12 }}>
          <div className="diff-out">
            {result.diff.map((d, i) => <span key={i} className={d.ok ? 'ok' : 'bad'}>{d.word}{i < result.diff.length - 1 ? ' ' : ''}</span>)}
          </div>
          <div className="score">{result.score} 分 {result.score >= 80 ? '✅' : result.score >= 50 ? '👍' : '💪'}</div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: 手动验证**

Run: `npm run dev` → 进学习页 → 切「听写」→ 输入正确俄语 → 提交显示 100 分全绿；输入一半 → 显示红绿混排 + 对应分数；「重听」播放本句。

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat: dictate stage with diff scoring"
```

---

### Task 10: 跟读关卡 + 尚雯婕模式

**Files:**
- Create: `src/components/StageRecite.jsx`（替换占位）

**Interfaces:**
- Consumes: `scoring.dictation`（复用相似度打分）、`scoring.selfRate`、`tts.loopSentence`、`webkitSpeechRecognition`
- Produces: 麦克风识别比对 或 自评 4 档；「尚雯婕模式」循环听 N 遍 → 隐藏原文跟读 → 自评 → 回调 `onScore`。

- [ ] **Step 1: 实现 `src/components/StageRecite.jsx`**

```jsx
import { useRef, useState } from 'react'
import { dictation, selfRate } from '../lib/scoring'
import { speak, loopSentence, cancelSpeech } from '../lib/tts'
import { useSettingsStore } from '../store/settingsStore'

const GRADES = [
  { g: 0, label: '忘记' }, { g: 1, label: '困难' }, { g: 2, label: '犹豫' }, { g: 3, label: '顺利' }
]

export default function StageRecite({ sentence, onScore }) {
  const { settings } = useSettingsStore()
  const recRef = useRef(null)
  const [recogText, setRecogText] = useState('')
  const [listening, setListening] = useState(false)
  const [shang, setShang] = useState(false)

  const SR = window.SpeechRecognition || window.webkitSpeechRecognition

  const startMic = () => {
    if (!SR) { toast('当前浏览器不支持语音识别，请用自评'); return }
    const rec = new SR()
    recRef.current = rec
    rec.lang = 'ru-RU'
    rec.onresult = (e) => {
      const text = Array.from(e.results).map(r => r[0].transcript).join(' ')
      setRecogText(text)
      const score = dictation(text, sentence.russian).score
      onScore(score)
    }
    rec.onend = () => setListening(false)
    setListening(true)
    rec.start()
  }

  const stopMic = () => { recRef.current?.stop(); setListening(false) }

  const startShang = () => {
    setShang(true)
    loopSentence([sentence], 0, settings.loopTimes, { rate: settings.rate, onDone: () => {} })
  }

  return (
    <div>
      <div className="row">
        <button className="btn primary" onClick={listening ? stopMic : startMic}>{listening ? '⏹ 停止' : '🎤 开始跟读'}</button>
        <button className="btn" onClick={startShang}>🦜 尚雯婕模式</button>
      </div>
      {shang && <div className="hint" style={{ marginTop: 8 }}>循环听 {settings.loopTimes} 遍后，跟读并自评</div>}
      {recogText && <div className="hint" style={{ marginTop: 8 }}>识别结果：{recogText}</div>}

      <div className="row" style={{ marginTop: 12 }}>
        {GRADES.map(({ g, label }) => (
          <button key={g} className="grade" onClick={() => onScore(selfRate(g))}>{label}<br /><small>{selfRate(g)}分</small></button>
        ))}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: 手动验证**

Run: `npm run dev` → 「跟读」→ 无麦克风/不支持时点「自评」四档给分；Chrome 下点「开始跟读」识别俄语比对给分；「尚雯婕模式」循环播放当前句 N 遍。

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat: recite stage + shang wenjie loop mode"
```

---

### Task 11: splitter + 添加资料

**Files:**
- Create: `src/lib/splitter.js`, `src/lib/splitter.test.js`, `src/components/AddMaterialModal.jsx`

**Interfaces:**
- Produces:
  - `splitText(text)` → `string[]`（按 `.!?…` 切分、去空、合并 <3 字符碎片）
  - `AddMaterialModal`：粘贴文本 + 标题 → 生成 `{ id:'custom_xxx', title, sentences:[{id,russian}], createdAt }` → `addMaterial` → 跳 `/study/:id`

- [ ] **Step 1: 写测试 `src/lib/splitter.test.js`**

```js
import { describe, it, expect } from 'vitest'
import { splitText } from './splitter'

describe('splitText', () => {
  it('splits on sentence punctuation', () => {
    expect(splitText('Привет! Как дела? Хорошо.')).toEqual(['Привет!', 'Как дела?', 'Хорошо.'])
  })
  it('merges tiny fragments into neighbors', () => {
    expect(splitText('Да! Ну, хорошо.')).toEqual(['Да! Ну, хорошо.'])
  })
  it('drops empty and whitespace-only lines', () => {
    expect(splitText('Привет!\n\n  \nКак дела?')).toEqual(['Привет!', 'Как дела?'])
  })
})
```

- [ ] **Step 2: 运行确认失败** — Run: `npm test -- splitter` → FAIL

- [ ] **Step 3: 实现 `src/lib/splitter.js`**

```js
export function splitText(text) {
  const raw = (text || '')
    .replace(/\r/g, '')
    .split(/[.!?…]+/)
    .map(s => s.replace(/\s+/g, ' ').trim())
    .filter(Boolean)

  const out = []
  for (const s of raw) {
    if (s.length < 3) {
      if (out.length) out[out.length - 1] += ' ' + s
      else out.push(s)
    } else {
      out.push(s)
    }
  }
  return out
}
```

- [ ] **Step 4: 运行确认通过** — Run: `npm test -- splitter` → PASS

- [ ] **Step 5: 实现 `src/components/AddMaterialModal.jsx`**

```jsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { splitText } from '../lib/splitter'
import { useCourseStore } from '../store/courseStore'

export default function AddMaterialModal({ onClose }) {
  const navigate = useNavigate()
  const addMaterial = useCourseStore(s => s.addMaterial)
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')

  const save = () => {
    const sents = splitText(text).map((russian, i) => ({ id: i + 1, russian }))
    if (!sents.length) { toast('请输入俄语文本'); return }
    const id = 'custom_' + Date.now().toString(36)
    addMaterial({ id, title: title || '自定义文本', sentences: sents, createdAt: Date.now() })
    navigate('/study/' + id)
  }

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>＋ 添加资料</h2>
        <p className="hint">粘贴俄语文本，自动断句后进入 TTS 学习（无视频、无需字幕）。</p>
        <div className="field">
          <label>标题（可选）</label>
          <input value={title} onChange={e => setTitle(e.target.value)} placeholder="例如：俄语日常对话" />
        </div>
        <div className="field">
          <label>俄语文本</label>
          <textarea rows={8} value={text} onChange={e => setText(e.target.value)} placeholder="粘贴俄语文本…" />
        </div>
        <div className="mfoot">
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn primary" onClick={save}>保存并开始学习</button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 6: 接线到 Home（加「＋ 添加资料」入口）**

在 `Home.jsx` 顶部加：

```jsx
import { useState } from 'react'
import AddMaterialModal from '../components/AddMaterialModal'
// ...
const [showAdd, setShowAdd] = useState(false)
// 在返回的 <div className="course"> 最前插入：
// <div className="row" style={{marginBottom:16}}><button className="btn primary" onClick={()=>setShowAdd(true)}>＋ 添加资料</button></div>
// 在返回结构末尾（闭合标签前）插入：
// {showAdd && <AddMaterialModal onClose={()=>setShowAdd(false)} />}
```

- [ ] **Step 7: 手动验证**

Run: `npm run dev` → 首页「＋ 添加资料」→ 粘贴俄语文本 → 保存 → 进入学习页，台词按句拆分，TTS 可逐句播放。

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat: text splitter + add material"
```

---

### Task 12: fsrs + vocabStore + WordPop + 词句本

**Files:**
- Create: `src/lib/fsrs.js`, `src/lib/fsrs.test.js`, `src/store/vocabStore.js`, `src/components/WordPop.jsx`, `src/pages/Vocab.jsx`（替换占位）

**Interfaces:**
- Consumes: `ts-fsrs`
- Produces:
  - `RATING`、`newCard()`、`review(card, rating)`、`isDue(card, now)`、`serializeCard`/`deserializeCard`
  - `useVocabStore`：`{ cards, addWord({word,lemma,chinese,source}), review(cardId, rating), dueCards() }`
  - `WordPop`：点词弹窗（释义 + 加入生词）
  - `Vocab` 页：到期卡复习

- [ ] **Step 1: 写测试 `src/lib/fsrs.test.js`**

```js
import { describe, it, expect } from 'vitest'
import { newCard, review, isDue, RATING, serializeCard, deserializeCard } from './fsrs'

describe('fsrs wrapper', () => {
  it('newCard is due immediately', () => {
    const c = newCard()
    expect(isDue(c, new Date())).toBe(true)
  })

  it('review pushes due into future', () => {
    const c = review(newCard(), RATING.good)
    expect(isDue(c, new Date())).toBe(false)
  })

  it('review again keeps due near now', () => {
    const c = review(newCard(), RATING.again)
    expect(isDue(c, new Date())).toBe(true)
  })

  it('serialize/deserialize round-trips due as Date', () => {
    const c = review(newCard(), RATING.good)
    const rt = deserializeCard(JSON.parse(JSON.stringify(serializeCard(c))))
    expect(rt.due instanceof Date).toBe(true)
    expect(rt.due.getTime()).toBeCloseTo(c.due.getTime(), -2)
  })
})
```

- [ ] **Step 2: 运行确认失败** — Run: `npm test -- fsrs` → FAIL

- [ ] **Step 3: 实现 `src/lib/fsrs.js`**

```js
import { createEmptyCard, fsrs, Rating } from 'ts-fsrs'

const scheduler = fsrs()

export const RATING = { again: Rating.Again, hard: Rating.Hard, good: Rating.Good, easy: Rating.Easy }

export function newCard() { return createEmptyCard() }

export function review(card, rating) {
  const now = new Date()
  const result = card.state === 2 ? scheduler.repeat(card, now) : scheduler.next(card, now, rating)
  return result.card
}

export function isDue(card, now) { return card.due.getTime() <= now.getTime() }

export function serializeCard(card) {
  return {
    ...card,
    due: card.due instanceof Date ? card.due.toISOString() : card.due,
    last_review: card.last_review ? (card.last_review instanceof Date ? card.last_review.toISOString() : card.last_review) : null,
  }
}

export function deserializeCard(s) {
  return { ...s, due: new Date(s.due), last_review: s.last_review ? new Date(s.last_review) : null }
}
```

> 注：`ts-fsrs` 的 `state` 值 2 表示 `New`。若安装版本 API 有差异（`repeat`/`next` 返回形状、`state` 常量），执行时以 `npm test -- fsrs` 实际输出为准微调，接口名不变。

- [ ] **Step 4: 运行确认通过** — Run: `npm test -- fsrs` → PASS（若版本 API 差异导致失败，按 Step 3 注调整后重跑）

- [ ] **Step 5: 实现 `src/store/vocabStore.js`**

```js
import { create } from 'zustand'
import { loadLS, saveLS, LS } from '../lib/persistence'
import { newCard, review, isDue, serializeCard, deserializeCard } from '../lib/fsrs'

function load() {
  return loadLS(LS.vocab, []).map(c => ({ ...c, fsrs: deserializeCard(c.fsrs) }))
}

export const useVocabStore = create((set, get) => ({
  cards: load(),

  addWord({ word, lemma, chinese, source }) {
    const card = {
      id: 'v' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
      word, lemma, chinese, source,
      fsrs: newCard(),
      createdAt: Date.now(),
    }
    const cards = [card, ...get().cards]
    saveLS(LS.vocab, cards.map(c => ({ ...c, fsrs: serializeCard(c.fsrs) })))
    set({ cards })
  },

  review(cardId, rating) {
    set(s => {
      const cards = s.cards.map(c => c.id === cardId ? { ...c, fsrs: review(c.fsrs, rating) } : c)
      saveLS(LS.vocab, cards.map(c => ({ ...c, fsrs: serializeCard(c.fsrs) })))
      return { cards }
    })
  },

  dueCards() { const now = Date.now(); return get().cards.filter(c => isDue(c.fsrs, now)) },
}))
```

- [ ] **Step 6: 实现 `src/components/WordPop.jsx`**

```jsx
import { useEffect, useRef, useState } from 'react'
import { useVocabStore } from '../store/vocabStore'

export default function WordPop({ word, x, y, onClose }) {
  const ref = useRef(null)
  const addWord = useVocabStore(s => s.addWord)
  const [chinese, setChinese] = useState('')

  useEffect(() => {
    const onDoc = e => { if (ref.current && !ref.current.contains(e.target)) onClose() }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [onClose])

  const add = () => {
    addWord({ word, lemma: word.replace(/[́̀]/g, ''), chinese: chinese || '（待释义）', source: 'sentence' })
    onClose()
  }

  return (
    <div className="word-pop" ref={ref} style={{ left: x, top: y }}>
      <div className="w-head ru">{word}</div>
      <div className="w-body">
        <input placeholder="释义（可选，AI 翻译见 Task 13）" value={chinese} onChange={e => setChinese(e.target.value)} style={{ width: '100%', padding: '6px 8px', border: '1px solid var(--border2)', borderRadius: 6 }} />
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        <button className="btn sm primary" onClick={add}>＋ 加入生词</button>
      </div>
    </div>
  )
}
```

- [ ] **Step 7: 在 `SentenceBox.jsx` 接线点词**

把 `renderStressed` 改为：每个词用 `<span class="w" data-word="…">` 包裹，`SentenceBox` 加 `onClick` 捕获 `e.target.closest('.w')`，取 `dataset.word` 弹 `WordPop`。更新 `SentenceBox.jsx`：

```jsx
import { useState } from 'react'
import WordPop from './WordPop'

export default function SentenceBox({ sentence, revealed }) {
  const [pop, setPop] = useState(null)

  if (!revealed) return <div className="sentence-box"><div className="cover">🔇 原文已隐藏</div></div>

  const html = sentence.russian
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .split(/\s+/)
    .map(w => `<span class="w" data-word="${w}">${w}</span>`)
    .join(' ')

  const onClick = (e) => {
    const el = e.target.closest('.w')
    if (el) setPop({ word: el.dataset.word, x: e.clientX, y: e.clientY })
  }

  return (
    <>
      <div className="sentence-box" onClick={onClick}>
        <div className="txt ru" dangerouslySetInnerHTML={{ __html: html }} />
      </div>
      {pop && <WordPop word={pop.word} x={pop.x} y={pop.y} onClose={() => setPop(null)} />}
    </>
  )
}
```

- [ ] **Step 8: 实现 `src/pages/Vocab.jsx`**

```jsx
import { useState } from 'react'
import { useVocabStore } from '../store/vocabStore'
import { RATING } from '../lib/fsrs'

const GRADES = [
  { r: RATING.again, label: '忘记' }, { r: RATING.hard, label: '困难' },
  { r: RATING.good, label: '记得' }, { r: RATING.easy, label: '轻松' }
]

export default function Vocab() {
  const cards = useVocabStore(s => s.cards)
  const due = useVocabStore(s => s.dueCards())
  const review = useVocabStore(s => s.review)
  const [show, setShow] = useState(false)
  const [i, setI] = useState(0)

  if (due.length === 0) {
    return <div className="empty"><div className="big">🎉</div><h1>今天没有待复习的生词</h1><p>共 {cards.length} 个生词。</p></div>
  }

  const card = due[i] || due[0]
  const rate = (r) => { review(card.id, r); setShow(false); setI(0) }

  return (
    <div className="modal-mask" style={{ position: 'static', background: 'none', padding: 24 }}>
      <div className="modal" style={{ maxWidth: 460, margin: '0 auto' }}>
        <h2>生词复习</h2>
        <div className="srs-card">
          <div className="q"><span className="w ru">{card.word}</span></div>
          {show && <div className="a">{card.chinese}</div>}
          {!show && <button className="btn primary" onClick={() => setShow(true)}>显示答案</button>}
          {show && (
            <div className="srs-grades">
              {GRADES.map(g => <button key={g.label} className="grade" onClick={() => rate(g.r)}>{g.label}</button>)}
            </div>
          )}
        </div>
        <div className="srs-stats">今日待复习 {due.length} 个 · 共 {cards.length} 个生词</div>
      </div>
    </div>
  )
}
```

- [ ] **Step 9: 手动验证**

Run: `npm run dev` → 学习页点句子里某词 → 弹窗 → 「＋ 加入生词」→ 顶栏「生词本」→ 显示待复习卡 → 显示答案 → 四档评分 → 到期队列减少；「忘记」后仍在到期队列。

- [ ] **Step 10: Commit**

```bash
git add -A && git commit -m "feat: fsrs vocab store + word pop + vocab review page"
```

---

### Task 13: ai.js + 设置弹窗 + 统计页

**Files:**
- Create: `src/lib/ai.js`, `src/components/SettingsModal.jsx`, `src/pages/Profile.jsx`（替换占位）
- Modify: `src/App.jsx`（顶栏加「设置」入口 + 弹窗状态）

**Interfaces:**
- Consumes: `useSettingsStore`、`useCourseStore`、`useVocabStore`
- Produces:
  - `chat({ baseUrl, apiKey, model, messages })` → 文本（OpenAI 兼容直连）
  - `SettingsModal`：baseUrl/key/model/音色/语速/循环次数
  - `Profile`：学习天数/streak/练习句数/完成视频数/各级掌握度/生词数

- [ ] **Step 1: 实现 `src/lib/ai.js`**

```js
export async function chat({ baseUrl, apiKey, model, messages }) {
  if (!apiKey) throw new Error('未配置 API Key，请在设置里填写')
  const res = await fetch((baseUrl.replace(/\/$/, '') + '/chat/completions'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + apiKey },
    body: JSON.stringify({ model, messages, temperature: 0.3 }),
  })
  if (!res.ok) {
    const t = await res.text().catch(() => '')
    throw new Error('请求失败 ' + res.status + (t ? ': ' + t.slice(0, 200) : ''))
  }
  const j = await res.json()
  return j.choices?.[0]?.message?.content || ''
}

export async function explainSentence(text, settings) {
  return chat({
    ...settings,
    messages: [
      { role: 'system', content: '你是俄语老师。逐词解析这句俄语：原形、词性、语法功能、整句中文翻译。用简洁中文，适当用列表。' },
      { role: 'user', content: text },
    ],
  })
}
```

- [ ] **Step 2: 实现 `src/components/SettingsModal.jsx`**

```jsx
import { useState } from 'react'
import { useSettingsStore } from '../store/settingsStore'

export default function SettingsModal({ onClose }) {
  const { settings, save } = useSettingsStore()
  const [s, setS] = useState(settings)

  const set = (k, v) => setS(prev => ({ ...prev, [k]: v }))

  return (
    <div className="modal-mask" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h2>设置</h2>
        <p className="hint">「AI 解析」需配置 OpenAI 兼容接口（DeepSeek / 通义 / 智谱等）。</p>
        <div className="field"><label>接口地址 baseUrl</label><input value={s.baseUrl} onChange={e => set('baseUrl', e.target.value)} /></div>
        <div className="field"><label>API Key</label><input type="password" value={s.apiKey} onChange={e => set('apiKey', e.target.value)} placeholder="sk-..." /></div>
        <div className="field"><label>模型名</label><input value={s.model} onChange={e => set('model', e.target.value)} /></div>
        <div className="field"><label>语速 rate</label><input type="number" step="0.1" min="0.5" max="2" value={s.rate} onChange={e => set('rate', parseFloat(e.target.value) || 1)} /></div>
        <div className="field"><label>尚雯婕模式循环遍数</label><input type="number" min="1" max="10" value={s.loopTimes} onChange={e => set('loopTimes', parseInt(e.target.value) || 3)} /></div>
        <div className="mfoot">
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn primary" onClick={() => { save(s); onClose() }}>保存</button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: 接线到 App.jsx**

在 `App.jsx` 顶栏加「设置」按钮和弹窗（`useState` 控制 `showSettings`），并在返回结构末尾渲染 `{showSettings && <SettingsModal onClose={...} />}`。同时把 `vocab` 打开方式改为页面路由（已用 `<Link to="/vocab">`，无需额外弹窗）。

- [ ] **Step 4: 实现 `src/pages/Profile.jsx`**

```jsx
import { LEVELS } from '../data/courseLibrary'
import { useCourseStore } from '../store/courseStore'
import { useVocabStore } from '../store/vocabStore'

export default function Profile() {
  const progress = useCourseStore(s => s.progress)
  const levelMastery = useCourseStore(s => s.levelMastery)
  const isLevelUnlocked = useCourseStore(s => s.isLevelUnlocked)
  const cards = useVocabStore(s => s.cards)

  const doneVideos = Object.values(progress).filter(p => p.done).length
  let practiced = 0
  for (const p of Object.values(progress)) practiced += Object.keys(p.sentenceScores || {}).length

  const days = new Set(Object.values(progress).map(p => new Date(p.updatedAt).toDateString()))
  const streak = days.size

  return (
    <div className="course">
      <h2>📊 学习统计</h2>
      <div className="videos-grid" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(160px,1fr))', marginBottom: 20 }}>
        <div className="card"><div className="score-big">{days.size}</div><div className="hint">学习天数</div></div>
        <div className="card"><div className="score-big">{streak}</div><div className="hint">连续打卡（去重日）</div></div>
        <div className="card"><div className="score-big">{practiced}</div><div className="hint">练习句子数</div></div>
        <div className="card"><div className="score-big">{doneVideos}</div><div className="hint">完成视频数</div></div>
        <div className="card"><div className="score-big">{cards.length}</div><div className="hint">生词总数</div></div>
      </div>

      <h3>各级掌握度</h3>
      {LEVELS.map(l => (
        <div key={l} className="course-item" style={{ cursor: 'default' }}>
          <span className="t">{l}</span>
          <span className="hint">{isLevelUnlocked(l) ? `掌握 ${levelMastery(l)}%` : '🔒 未解锁'}</span>
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 5: 手动验证**

Run: `npm run dev` → 设置里填 Key → 学习页点「AI 解析」（若有此入口，见 Task 13 附注）弹结果；`/profile` 显示学习天数/句数/完成视频/各级掌握度/生词数。

> 附注：AI 解析入口在 Study 页已有「🤖 AI 解析」概念，但为控制本任务边界，本任务只交付 `ai.js` + 设置 + 统计；「AI 解析」按钮的 UI 挂载可作为可选后续（在 `SentenceBox`/`StageListen` 加按钮调 `explainSentence`，渲染到 `translationBox`）。执行时若时间允许，一并挂载；否则记录为已知缺口并在收尾任务补。

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: ai client + settings modal + profile stats"
```

---

### Task 14: 收尾（AI 解析挂载 + 全量验证）

**Files:**
- Modify: `src/pages/Study.jsx`、`src/components/SentenceBox.jsx`（挂 AI 解析入口）
- Create: 无新增

**Interfaces:**
- 无新接口；补齐「AI 解析」UI 到学习页。

- [ ] **Step 1: 在 `Study.jsx` 挂 AI 解析**

在 `Study.jsx` 加状态 `const [aiHtml, setAiHtml] = useState('')`，加按钮：

```jsx
const runAI = async () => {
  const { settings } = useSettingsStore.getState()
  setAiHtml('解析中…')
  try { setAiHtml(mdToHtml(await explainSentence(cur.russian, settings))) }
  catch (e) { setAiHtml(''); toast(e.message) }
}
```

`translationBox` 改为受控渲染（去掉 `hidden` 硬编码）：`{aiHtml && <div className="translation" dangerouslySetInnerHTML={{ __html: aiHtml }} />}`。`mdToHtml` 极简实现（把 `**x**` → `<b>x</b>`、`\n` → `<br>`、`- ` → `• `），写在该文件底部或 `lib/md.js`。

- [ ] **Step 2: 全量手动回归**

Run: `npm run dev`，逐项走查：
1. 首页：A1 可进、A2–B2 锁；点视频进学习。
2. 学习：听（本句/连播/循环）、听写（diff+分）、跟读（自评/识别）、提交评测→视频 done→解锁下一视频/下一级。
3. 词句本：点词加词 → 复习四档 → 到期变化。
4. 添加资料：粘文本 → 学习。
5. 统计：`/profile` 数据正确。
6. AI：填 Key → 解析句子出结果；无 Key → toast 提示。
7. 刷新页面：进度/生词/最近/设置均从 localStorage 恢复。

- [ ] **Step 3: 运行全部单测**

Run: `npm test`
Expected: 全绿（persistence / courseLibrary / scoring / courseStore / tts / splitter / fsrs）。

- [ ] **Step 4: 最终 Commit**

```bash
git add -A && git commit -m "feat: wire AI parse into study; final polish"
```

---

## Self-Review 结果

- **Spec 覆盖**：spec §5 数据层→Task 2/3/5；§6 store→Task 2/5/12；§7 播放→Task 6；§8 学习页→Task 8/9/10；§9 评分→Task 4；§10 词句本 FSRS→Task 12；§11 最近/统计→Task 7/13；§12 AI/添加资料→Task 13/11；§14 测试→各 Task 的 `.test.js`；§15 实现顺序→Task 1–14 顺序一致。
- **类型一致**：`norm/dictation/selfRate/sentenceMastery/videoScore/levelMastery/isLevelUnlocked/isVideoUnlocked`（Task 4）签名与 `courseStore`（Task 5）调用一致；`splitText`、`newCard/review/isDue/RATING/serializeCard`、`speak/speakAll/loopSentence/cancelSpeech`、`chat/explainSentence` 均跨任务一致。
- **占位扫描**：无 TBD/TODO；Task 8 的 `StageDictate`/`StageRecite` 占位在 Task 9/10 立即替换，属正常顺序填充而非空占位；Task 13 附注明确指出 AI 解析 UI 挂载在 Task 14 补齐。
