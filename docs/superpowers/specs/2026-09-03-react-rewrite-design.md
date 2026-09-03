# 看视频学俄语 — React 重写设计文档

日期：2026-09-03
项目：`russian-learning`（现有单文件 vanilla JS 应用 → React 重写）

## 1. 背景与目标

现有应用是单文件 `index.html`（约 2600 行 vanilla JS）+ `server.py` 本地后端，功能已较完整（分级课程库、逐句听/听写/跟读、生词本 SM-2、AI 解析、词典、语法、Whisper 转写等）。

经与用户确认，本任务**重写为 React**，并**新增预置课程库**（带预置句子 + TTS 离线播放），**只做 spec 范围**的功能，不迁移词典/语法/Whisper/AI 断句预览。

### 目标（v1）

- React + Vite + React Router + Zustand 全新前端。
- 预置 A1–B2 课程库（collections → videos → sentences），**TTS 离线播放**（无真实视频、无 server 依赖）。
- 完整学习闭环：逐句 **听 / 听写 / 跟读（背诵）** + 评分系统 + 学习进度 + 分级解锁。
- 词句本（**FSRS** 间隔重复）、最近观看、学习统计。
- 「添加资料」= 粘贴俄语文本 → 断句 → TTS 学习。
- AI 解析（可选，浏览器直连 OpenAI 兼容接口）。

### 非目标（v1 不做）

- 俄语词典（变格表）、俄语语法工具书、Whisper 音频转写、AI 断句预览、AI 学习教练 —— 均保留在旧 `legacy.html` 中，不迁移。
- 真实 `<video>` 播放、真实时间轴字幕同步（`start/end` 字段本版不使用）。
- 后端 `server.py` 本版不需要（核心全离线）；旧文件原样保留。

## 2. 关键决策（已与用户确认）

| 决策点 | 结论 |
|--------|------|
| 技术栈 | React 18 + Vite + React Router 6 + **Zustand**（非 Context） |
| 课程库数据 | 新增预置 `courseLibrary`（静态、只读、带预置句子） |
| 播放方式 | Web Speech API `speechSynthesis`（`ru-RU`）句级播放，`posterUrl` 作封面 |
| 同步高亮 | 句级高亮，由 `utterance.onstart/onend` 驱动，**不使用** `start/end` |
| 移植范围 | 只做 spec 范围（课程库/学习/词句本/最近/统计/AI/添加资料） |
| FSRS 实现 | `ts-fsrs` 官方包（FSRS 算法正确性优先） |
| 添加资料形态 | 粘贴俄语文本 → 断句 → TTS（无视频/无 server/无 Whisper） |
| AI 解析 | 浏览器直连 OpenAI 兼容接口（默认 DeepSeek，支持 CORS） |

## 3. 技术栈与依赖

- 运行时：`react`、`react-dom`、`react-router-dom`、`zustand`、`ts-fsrs`
- 构建：`vite`、`@vitejs/plugin-react`
- 无 Tailwind：沿用现有设计系统（CSS 变量 + 现有样式类），以 `<style>` 或普通 CSS 文件方式保留视觉，不引 Tailwind 构建链。

## 4. 项目结构

```
russian-learning/
├─ index.html                 # Vite 入口（新建）
├─ legacy.html                # 旧单文件前端（改名保留，含词典/语法/Whisper）
├─ server.py  data/  *.js     # 旧后端/数据，原样保留不动
├─ package.json  vite.config.js
└─ src/
   ├─ main.jsx                # 挂载 + BrowserRouter
   ├─ App.jsx                 # 路由 + 顶栏布局
   ├─ styles.css              # 沿用现有设计系统（CSS 变量 + 组件类）
   ├─ data/
   │  └─ courseLibrary.js     # 静态课程库（预置句子）
   ├─ store/
   │  ├─ courseStore.js       # 课程进度 / 解锁 / 最近观看
   │  ├─ vocabStore.js        # 词句本 + FSRS 调度
   │  ├─ sessionStore.js      # 当前学习会话（当前视频/句子/关卡）
   │  └─ settingsStore.js     # 设置（AI key、音色、循环次数等）
   ├─ lib/
   │  ├─ tts.js               # TTS 播放引擎（句级播放/连播/循环）
   │  ├─ fsrs.js              # 封装 ts-fsrs（创建/复习/到期队列）
   │  ├─ scoring.js           # 听写/跟读打分、句子/视频/等级掌握度
   │  ├─ splitter.js          # 俄语文本断句
   │  ├─ ai.js                # OpenAI 兼容直连（AI 解析/翻译）
   │  └─ persistence.js       # localStorage 读写 + 版本化
   ├─ pages/
   │  ├─ Home.jsx             # 等级选择 + 筛选 + 视频卡片 + 最近观看
   │  ├─ Study.jsx            # 学习页
   │  ├─ Vocab.jsx            # 词句本复习
   │  └─ Profile.jsx          # 学习统计
   └─ components/
      ├─ VideoCard.jsx        # 课程视频卡片
      ├─ SentenceList.jsx     # 台词列表（高亮 + 点击）
      ├─ SentenceBox.jsx      # 当前句子展示（点词翻译）
      ├─ StageListen.jsx      # 听
      ├─ StageDictate.jsx     # 听写
      ├─ StageRecite.jsx      # 跟读/背诵（含尚雯婕模式）
      ├─ WordPop.jsx          # 点词释义弹窗
      ├─ AddMaterialModal.jsx # 添加资料
      └─ SettingsModal.jsx    # 设置
```

## 5. 数据层

### 5.1 静态课程库（`src/data/courseLibrary.js`，只读）

```js
export const LEVELS = ['A1', 'A2', 'B1', 'B2'];

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
            description: '学习最基础的俄语问候语、自我介绍句型。',
            thumbnail: 'https://picsum.photos/seed/ru_greet_01/400/280',
            posterUrl: 'https://picsum.photos/seed/ru_greet_01/1280/720',
            level: 'A1',
            duration: '4:30',          // 仅展示
            words: 120,
            tags: ['慢速', '基础', '口语'],
            learners: 128,
            sentences: [
              { id: 1, russian: 'Здра́вствуйте!', chinese: '您好！', stressed: 'Здра́вствуйте!' },
              { id: 2, russian: 'Меня́ зову́т Анна.', chinese: '我叫安娜。', stressed: 'Меня́ зову́т Анна.' }
              // 每视频 15–20 句
            ]
          }
        ]
      }
    ]
  }
  // A2 / B1 / B2 同构
};
```

- 句子字段：`{ id, russian, chinese, stressed? }`。`russian` 为含重音符号的展示原文（用于点词与朗读）；`stressed` 可选（缺省等于 `russian`，用于重音高亮着色）。**不含 `start/end`**（TTS 句级播放不需要；未来接真实音频再补）。
- `videoUrl` 字段省略（本版无真实视频）。
- 内容量：4 级全有、每级 ≥1 合集、每级 1–2 个视频、每视频 15–20 句，共约 120–200 句（带重音 + 中文）。

### 5.2 用户状态（localStorage，前缀 `rlearn_v1`）

```js
{
  course: {                    // key: videoId（含 custom_*）
    [videoId]: {
      done: bool,
      score: 0..100,           // 视频得分
      sentenceScores: {        // key: sentenceId
        [sid]: { dictate?: 0..100, recite?: 0..100 }
      },
      lastIndex: int,          // 上次学到第几句
      updatedAt: number
    }
  },
  vocab: [ {                   // FSRS 卡片
    id, word, lemma, chinese, source,
    fsrs: <ts-fsrs Card state>, createdAt
  } ],
  recent: [ { videoId, updatedAt } ],   // 最近观看，按 updatedAt 降序，最多 10 条
  materials: [ {               // 添加资料的自定义文本
    id: 'custom_xxx', title, posterUrl:null, sentences:[{id,russian,chinese?,stressed?}], createdAt
  } ],
  settings: {
    baseUrl: 'https://api.deepseek.com', apiKey: '', model: 'deepseek-chat',
    voiceURI: '', rate: 1.0, loopTimes: 3
  }
}
```

### 5.3 持久化

- `persistence.js` 封装 `loadLS(key, def)` / `saveLS(key, val)`，带 `try/catch`。
- 每个 Zustand store 内部 `subscribe` 或显式调用把状态写回 localStorage；课程库静态数据不落盘。
- 课程进度 key 统一用 `videoId`（课程视频用其 `id`，自定义用 `custom_*`）。

## 6. 状态管理（Zustand）

- `courseStore`：`progress`（上表 course）、`recent`；actions：`getVideo(videoId)`（静态库 + 自定义材料合并查）、`recordScore`、`submitVideo`、`resetLevel`、`pushRecent`、`levelMastery`/`isLevelUnlocked`/`isVideoUnlocked` 派生。
- `vocabStore`：`cards`；actions：`addWord`、`review(cardId, rating)`（走 FSRS）、`dueCards()`。
- `sessionStore`：`videoId`、`curIdx`、`stage`（`listen|dictate|recite`）、`revealed`、`sentenceScores`（内存中，提交时落盘）。
- `settingsStore`：上表 settings；actions：`save`。

## 7. 播放 & 同步（`lib/tts.js`）

- 封装 `speechSynthesis`：`speak(text, {voiceURI, rate, onStart, onEnd})`，内部 `cancel()` 前一次播放。
- **句级高亮**：`playSentence(i)` → 设 `session.curIdx=i`，`utterance.onstart` 高亮、`onend` 清除（或连播时推进下一句）。
- **连播**：`playAll(from)` 顺序播全部句子并自动高亮，播完停止；「循环听」= 连播 + 自动重头。
- **逐句循环**（尚雯婕）：`loopSentence(i, n)` 对第 i 句重复播 n 遍。
- 音色：默认 `ru-RU`；`getVoices()` 加载后若存在俄语音色则选用，否则用浏览器默认；设置里可切换、可调速。

## 8. 学习页（`Study.jsx`）

- 路由 `/study/:videoId`；加载后 `pushRecent(videoId)`。
- 布局：左侧封面（poster）+ 台词列表；右侧关卡面板 + 当前句 + 翻译 + 操作行 + 上一句/下一句。
- 三关卡（`stage`）：**听 / 听写 / 跟读**。
  - **听**：原文隐藏；按钮「▶ 播放本句 / 全文连播 / 循环听 / 显示原文 / 中译」。
  - **听写**：`<textarea>` 输入，点「提交」调 `scoring.dictation()`，红绿 diff + 分数。
  - **跟读/背诵**：麦克风识别（`webkitSpeechRecognition`，`lang='ru-RU'`）比对，或自评 4 档；给分。
- **尚雯婕模式**：跟读关卡的显式子模式 —— 对当前句「循环听 N 遍（默认 3）→ 隐藏原文跟读 → 自评 → 自动下一句」。
- **点词翻译**：点击 `russian` 里任意单词 → `WordPop` 弹释义（本地词典缓存 / 可选 AI）→「＋ 加入生词」。
- **提交评测**：`submitVideo` 计算视频得分、写 `done`、刷新解锁。
- 顶部/侧栏显示进度（已练 n / 总 N，当前句得分）。

## 9. 评分系统（`lib/scoring.js`）

- `norm(s)`：去标点、去重音符号、小写、合并空格。
- `dictation(input, target)`：按**词**对齐（先 `norm` 成词序列，再 LCS + 回溯）→ 正确词标绿、错/漏词标红 → 返回 `{ score: 0..100, diff }`；`score = 正确词数 / 目标词数 × 100`。
- `recitation(recognized, target)`：同 `dictation` 的相似度打分；无法识别时走自评。
- `selfRate(g)`：4 档 → `{0:0, 1:35, 2:70, 3:100}`（忘记/困难/犹豫/顺利）。
- `sentenceMastery(sentenceScores[sid])`：已有 `dictate`/`recite` 分的平均；只有一个取其一；两者都有取平均。
- `videoScore(sentenceScores)`：已练句子的 mastery 平均（0..100）。
- `levelMastery(level, progress)`：该级所有 `done` 视频 score 的加权平均（未完成不计入）。
- 解锁：`isLevelUnlocked(level)` = 上一级 `levelMastery ≥ 60`；`isVideoUnlocked(level, i)` = 本级解锁 且（首视频 或 前一个视频 done）。

## 10. 词句本 + FSRS（`lib/fsrs.js` + `Vocab.jsx`）

- 用 `ts-fsrs`：默认 `createEmptyCard()` 建卡，`fsrs.repeat(card, now)` 生成到期卡片。
- 评分 4 档 `Rating.Again / Hard / Good / Easy`。
- `addWord(word, lemma, chinese, source)` → 建卡入 `vocabStore`。
- `dueCards()`：`card.due <= Date.now()` 的队列。
- `/vocab`：逐卡展示 `word`（隐藏释义）→ 点「显示答案」→ 4 档评分 → `review()` 更新卡片并重排到期队列；展示「今日待复习 / 共 N 个」统计。

## 11. 最近观看 + 学习统计

### 11.1 最近观看（首页）

- `pushRecent(videoId)`：进入学习页时调用，upsert `{videoId, updatedAt}`，降序截断到 10 条。
- 首页「最近观看」区块渲染这些视频卡片（含进度条）。

### 11.2 学习统计（`Profile.jsx`）

- 学习天数（有学习记录的去重日期数）、连续打卡 streak、累计练习句子数、完成视频数、各级掌握度、词句本总量、累计复习次数。
- 记录来源：`progress` 里各视频的 `sentenceScores`/`done`/`updatedAt` + `vocab` 复习日志（`vocabStore` 维护 `reviewLog` 数组）。

## 12. AI 解析 + 添加资料

### 12.1 AI 解析（`lib/ai.js`，可选）

- `chat(messages)`：`fetch(baseUrl + '/chat/completions', { Authorization: Bearer apiKey, model })`，OpenAI 兼容，浏览器直连。
- 「AI 解析」按钮 → 发当前俄语句 → 返回词逐解析（词形/原形/语法/翻译），`mdToHtml` 渲染。
- 未配 key 时 `toast` 提示去设置填 Key；直连 CORS 失败时提示改用兼容代理。

### 12.2 添加资料（`AddMaterialModal.jsx`）

- 粘贴俄语文本（可附标题）→ `splitter.js` 按标点断句 → 生成 `materials` 里一条 `{ id:'custom_xxx', sentences:[{russian}] }`（`chinese` 留空，可后点 AI 逐句翻译）→ 直接进入 `/study/custom_xxx`。
- 断句规则：按 `.!?…` 切分，去空行、去首尾空格，合并极短碎片（<3 字符并入相邻）。

## 13. 错误处理

| 场景 | 处理 |
|------|------|
| 无俄语 TTS 音色 | 用浏览器默认音色，设置里提示；不影响功能 |
| 语音识别不支持（Firefox/Safari） | 跟读自动回落「自评」按钮 |
| AI 未配 key / 直连 CORS 失败 / 网络错 | `toast` 可读提示，不崩溃 |
| localStorage 满 / 解析失败 | `try/catch`，降级为默认空状态 |
| 无效 videoId 路由 | 跳回首页并提示 |

## 14. 测试

1. **单元**（`vitest` 或 `node:test`）：`scoring`（dictation 打分/diff、norm、mastery 计算）、`splitter`（断句边界、极短碎片合并）、`fsrs` 封装（建卡/复习后 due 递增）、解锁逻辑（`isLevelUnlocked`/`isVideoUnlocked`）。
2. **数据完整性脚本**：校验 `courseLibrary` 每级非空、句子字段齐全、`id` 唯一、无占位空句。
3. **手动全流程**：首页选级 → 进学习 → 听/听写/跟读 → 提交得分 → 解锁下一级 → 加生词 → /vocab 复习 → /profile 统计 → 添加资料 → AI 解析。
4. **异常路径**：无 key AI、Firefox 无语音识别、无效路由、localStorage 损坏。

## 15. 实现顺序（分阶段）

1. **P0 骨架 + 数据层**：Vite 初始化、路由、`courseLibrary` 数据、Zustand 四个 store、`persistence`。
2. **P0 播放 + 学习闭环**：`tts.js`、`Study.jsx` 三关卡、`scoring.js`、进度 + 解锁。
3. **P1 增强**：点词翻译 + `WordPop`、词句本 + FSRS、最近观看、添加资料。
4. **P2 收尾**：AI 解析、`Profile` 统计、设置弹窗、样式打磨、测试补齐。
