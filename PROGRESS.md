# 旧网页全功能复刻到新 React app — 进度跟踪

> **目标**：把 `legacy.html`（单文件 vanilla JS）里的全部功能完整迁移到新 React app（`src/`）。
> 本文档用于断点续传，每次开工先读这里。

---

## 0. 启动

```bash
# 新 app 开发
cd "C:\Users\张宏飞\russian-learning"
启动-react.bat          # 等价于 npm run dev -- --open，访问 http://localhost:5173

# 测试
npm test                # vitest run

# 旧 app（仅做对照）
启动.bat                # python server.py，访问 http://localhost:8000
```

---

## 1. 旧 app 功能清单（要复刻的全部内容）

| 类别 | 功能 | 旧位置 | 状态 |
|---|---|---|---|
| 顶栏 | 品牌 / 首页 / 材料下拉 / 设置 | legacy.html:245-257 | ✅ App.jsx 已有 |
| 顶栏 | 「+ 导入材料」入口 | legacy.html:251 | ✅ App.jsx Home 已有 |
| 顶栏 | 「🎙 音频识别」入口 | legacy.html:252 | ❌ |
| 顶栏 | 「📖 词典」入口 | legacy.html:253 | ❌ |
| 顶栏 | 「📚 语法」入口 | legacy.html:254 | ❌ |
| 顶栏 | 「生词本」入口 | legacy.html:255 | ✅ Vocab 页已有 |
| 顶栏 | 「设置」入口 | legacy.html:256 | ✅ SettingsModal 已有 |
| 首页 | 模式选择卡（自定义素材 / 课程库） | legacy.html:260-275 | ❌（Home 已改为课程库） |
| 课程库 | A1–B2 分级 + 视频下载 + 进入学习 | legacy.html:570-660 | ❌ |
| 课程库 | 重置本等级 / 重置本视频 | legacy.html:797-806 | ❌ |
| 课程库 | 提交评测算得分、解锁下一视频 | legacy.html:781-795 | ❌（courseStore.submitVideo 有，但 UI 缺失） |
| 导入 | YouTube / 本地视频 / SRT/VTT/纯文本 | legacy.html:347-385 | ❌（AddMaterialModal 只有纯文本） |
| 导入 | 「⚡ 自动抓字幕」调 /api/subs | legacy.html:1985-1996 | ❌ |
| 导入 | AI 智能断句 + 预览/重生成/接受 | legacy.html:1109-1251 | ❌ |
| 导入 | 「用示例数据试试」 | legacy.html:2136-2142 | ❌ |
| 音频识别 | 粘贴 YouTube 链接 → faster-whisper 转写 | legacy.html:2074-2131 | ❌ |
| 学习 | 视频播放器（YouTube / 本地 / B 站流） | legacy.html:820-936 | ❌（Study 只显示 poster 图片） |
| 学习 | 字幕随播放时间高亮 | legacy.html:907-936 | ❌ |
| 学习 | 三关听 → 听写 → 跟读 | legacy.html:1733-1791 | ✅ Study + Stage* 有 |
| 学习 | 整段跟读模式（全文） | legacy.html:1752-1781 | ❌（只有单句） |
| 学习 | 「重读循环本句」（跟读 + 录音并行） | legacy.html:1865-1910 | ❌ |
| 学习 | 「中译」整段翻译缓存 | legacy.html:1921-1937 | ❌（Study 只有 showZh 单句） |
| 学习 | 「🤖 AI 解析」（俄语老师 prompt） | legacy.html:1952-1969 | ✅ Study.runAI 有 |
| 学习 | 点词弹窗 → 查译 / + 生词 | legacy.html:1585-1616 | ✅ WordPop 已有 |
| 生词本 | 弹窗复习（四档评级 SM-2） | legacy.html:2147-2180 | ❌（Vocab 是独立页 FSRS） |
| 词典 | 俄→中词典 + 变格/变位原型还原 | legacy.html:2241-2429 | ❌（dict-data.js / dict-full.js 已有数据） |
| 词典 | 词典词表 + 联网翻译（dict 缓存） | legacy.html:1572-1583 | ❌（/api/dict 接口已有） |
| 词典 | 「🤖 AI 助教：几格？为什么用？」 | legacy.html:2376-2402 | ❌ |
| 语法 | 内置 RU_GRAMMAR 数据 + 搜索 | legacy.html:2434-2476 | ❌（grammar-data.js 已有数据） |
| AI 教练 | 出题 / 批改 / 报告（pass/review/fail） | legacy.html:2478-2607 | ❌ |
| AI 教练 | 「下一篇」按钮（未通过则锁） | legacy.html:2601-2613 | ❌ |
| 设置 | baseUrl / Key / Model / Whisper 模型 | legacy.html:387-423 | ❌（SettingsModal 没有 Whisper） |
| 设置 | 导出备份 / 导入备份 | legacy.html:2198-2217 | ❌ |
| 通用 | toast、Esc 关闭弹窗、← → 翻句、空格播放 | legacy.html:2228-2236 | ❌ |
| 通用 | SRT/VTT 解析 + 断句 + 规则切句 | legacy.html:949-1108 | ❌（splitter 简版已有） |
| 通用 | 旧 localStorage → 新 localStorage 迁移 | — | ❌ |

**统计**：约 30 项功能，新 app 已覆盖 ~7 项，**待补 ~23 项**。

---

## 2. 新 app 已有结构（基线）

```
src/
├── main.jsx                     ✅ BrowserRouter + StrictMode
├── App.jsx                      ✅ 顶栏 + 路由（Home/Study/Vocab/Profile + Settings）
├── pages/
│   ├── Home.jsx                 ✅ 课程库主页（无需改，新增「导入材料 / 转写 / 词典 / 语法」入口）
│   ├── Study.jsx                ✅ 学习主页
│   ├── Vocab.jsx                ✅ 生词复习（FSRS，独立页）
│   └── Profile.jsx              ✅ 统计
├── components/
│   ├── VideoCard.jsx            ✅ 课程视频卡
│   ├── SentenceList.jsx         ✅ 句子列表
│   ├── SentenceBox.jsx          ✅ 句子框（点词）
│   ├── WordPop.jsx              ✅ 单词弹窗
│   ├── StageListen.jsx          ✅ 听
│   ├── StageDictate.jsx         ✅ 听写
│   ├── StageRecite.jsx          ✅ 跟读（基础）
│   ├── AddMaterialModal.jsx     ⚠️ 只有纯文本 → 需扩为完整导入
│   └── SettingsModal.jsx        ⚠️ 无 Whisper / 备份 → 需扩展
├── store/
│   ├── courseStore.js           ✅ progress / recent / materials + level 解锁
│   ├── sessionStore.js          ✅ 当前学习 session
│   ├── vocabStore.js            ✅ FSRS 生词
│   └── settingsStore.js         ⚠️ 无 whisperModel / 无 backup 操作
├── lib/
│   ├── persistence.js           ✅ rlearn_v1_* LS
│   ├── fsrs.js                  ✅ ts-fsrs 包装
│   ├── scoring.js               ✅ LCS 听写 / 自评 / 视频分
│   ├── tts.js                   ✅ Web Speech
│   ├── splitter.js              ✅ 标点断句
│   ├── ai.js                    ✅ OpenAI 兼容 chat
│   ├── md.js                    ✅ 简易 markdown
│   └── toast.js                 ✅ toast
└── test/setup.js
```

后端 `server.py` 已有：`/api/subs`、`/api/segment`、`/api/dict`、`/api/ai`、`/api/stream`、`/api/transcribe`。

数据资产（在仓库根）：
- `dict-data.js` — 简版高频词典（lemma→zh）
- `dict-full.js` — 全词典（lemma→{p,g,sg,pl,pres,past,imp,part,e,...}）
- `grammar-data.js` — `RU_GRAMMAR`（章节 + items 表/文本）

---

## 3. 复刻任务清单（按依赖顺序排）

| # | 任务 | 涉及文件 | 状态 |
|---|---|---|---|
| 1 | **公共 lib**：`mdToHtml` 加强（标题/代码/列表嵌套），新增 `parseSubtitles` / `cuesToSentences` / `plainToSentences` / `findLemma` / `parseAIJSON` / `callAI` / `norm` 共享 | `src/lib/srt.js`、`src/lib/lemma.js`、`src/lib/md.js` | ⬜ |
| 2 | **导入材料弹窗升级**：YouTube/本地/SRT-VTT-纯文本/⚡自动抓字幕/AI 断句预览/示例 | `src/components/AddMaterialModal.jsx`（改） + 新增 `src/components/SegPreviewModal.jsx` | ⬜ |
| 3 | **音频识别弹窗**（faster-whisper → 时间戳句子） | `src/components/TranscribeModal.jsx`（新） | ⬜ |
| 4 | **词典弹窗**（内置 + 变格还原 + 联网 + AI 助教） | `src/components/DictionaryModal.jsx`（新） + `src/lib/dictData.js` 引用 `dict-data.js` `dict-full.js`（新） | ⬜ |
| 5 | **语法工具书弹窗**（左导航 + 搜索） | `src/components/GrammarModal.jsx`（新） + `src/lib/grammarData.js`（新） | ⬜ |
| 6 | **AI 学习教练**（出题/作答/批改/报告/下一篇） | `src/components/CoachPanel.jsx`（新） + Study.jsx（接入） | ⬜ |
| 7 | **课程库 + 视频下载 + 重置 + 提交评测** | `src/pages/Course.jsx`（新） + `src/components/LevelList.jsx`（新） + `src/components/VideoItem.jsx`（新） | ⬜ |
| 8 | **点词查译 / 加入生词**（沿用 WordPop，但补弹层定位/原文翻译） | `src/components/WordPop.jsx`（小改） | ⬜ |
| 9 | **跟读阶段补全**：整段模式 / 重读循环本句 / 全文高亮 | `src/components/StageRecite.jsx`（改） + `src/components/StageListen.jsx`（补整段） | ⬜ |
| 10 | **顶栏入口 + 顶栏下拉**（自定义素材 / 课程库 / 导入 / 音频识别 / 词典 / 语法 / 设置 / 生词本） | `src/App.jsx`（改） | ⬜ |
| 11 | **设置升级**：加 Whisper / 导出备份 / 导入备份 | `src/components/SettingsModal.jsx`（改） + `src/store/settingsStore.js`（加 backup） | ⬜ |
| 12 | **键盘快捷键 / Esc 关闭** | `src/main.jsx` 或新建 `src/lib/keyboard.js` | ⬜ |
| 13 | **旧数据迁移**（`rulearn_*` → `rlearn_v1_*`） | `src/lib/migrate.js`（新） + `src/main.jsx` 顶部 import | ⬜ |
| 14 | **测试**：splitter / srt / migrate / Coach（mock AI） | `src/lib/*.test.js` 增量 | ⬜ |

---

## 4. 关键设计决策

1. **数据存储扩展**：settings 加 `whisperModel: 'small'`；不新建 backup store，用一次性函数 `exportBackup() / importBackup(json)` 直接读写 LS。
2. **课程库与 Home 合并**：保留 `pages/Home.jsx` 作为「最近 + 分级列表」主页（已有），把课程库下载流程挂到 `VideoCard` 上（点击 → 弹下载/进度/开始/重置弹窗）。**不**另开 `/course` 路由。
3. **AI 教练归属**：放 Study 页底部（与旧 app 一致），是 `<CoachPanel>` 组件。
4. **断句复用**：旧 `plainToSentences` / `cuesToSentences` 直接搬过来（`src/lib/srt.js`），并保留 `ruSegment()` 调后端 `/api/segment` razdel。
5. **Video 播放**：YouTube 用 `<iframe>` + YouTube IFrame API；本地用 `<video>` + IndexedDB；B 站等流媒体走后端 `/api/stream?url=` 代理。逐句高亮由 `timeupdate` 驱动。
6. **AI 断句预览**：弹窗接受 `SegPreviewModal`，可输入「修改意见」重新生成（连续走 `aiSegmentFromCues`）。
7. **动效一致性**：所有新弹窗沿用 `.modal-mask` + `.modal`，点击遮罩关闭；toast 用现成 `src/lib/toast.js`。
8. **不破坏现有测试**：每个新 lib 配套 `.test.js`，单测通过后再合进 UI。

---

## 5. 断点 / 待办（按当前进度填空）

- [x] 完成现状盘点（旧 vs 新对比清单）
- [x] 写 PROGRESS.md（本文件）
- [x] **#1 公共 lib**：`mdToHtml` 加强 / `parseSubtitles` / `plainToSentences` / `findLemma` / `parseAIJSON` / `callAI` / `norm` — 路径 `src/lib/srt.js`、`src/lib/lemma.js`、`src/lib/md.js`
- [x] **#2 导入材料弹窗**（AddMaterialModal 升级 + SegPreviewModal + segmenter + SettingsModal 加 Whisper/备份）
- [ ] #3 音频识别弹窗
- [ ] #4 词典弹窗
- [ ] #5 语法弹窗
- [ ] #6 AI 教练
- [ ] #7 课程库
- [ ] #8 WordPop 小改
- [ ] #9 跟读阶段补全
- [ ] #10 顶栏入口
- [ ] #11 顶栏下拉 / 材料下拉
- [ ] #12 键盘快捷键
- [ ] #13 旧数据迁移
- [ ] #14 测试覆盖

---

## 6. 复刻时随时参考的「旧 app → 新 app」对应路径

| 旧函数 | 旧位置 | 新位置（计划） |
|---|---|---|
| `parseSubtitles` | legacy.html:950-967 | `src/lib/srt.js` |
| `cuesToSentences` | legacy.html:968-1027 | `src/lib/srt.js` |
| `plainToSentences` | legacy.html:1028-1108 | `src/lib/srt.js` |
| `ruSegment` | legacy.html:1121-1128 | `src/lib/srt.js`（调 `/api/segment`） |
| `mdToHtml` | legacy.html:1942-1951 | `src/lib/md.js`（已有，加强） |
| `callAI` / `parseAIJSON` | legacy.html:2497-2510 | `src/lib/ai.js`（新加 `callAI`/`parseAIJSON`） |
| `findLemma` / 词典 | legacy.html:2249-2429 | `src/lib/lemma.js` + `src/components/DictionaryModal.jsx` |
| `openWordPop` / `addWord` | legacy.html:1585-1616 | `src/components/WordPop.jsx`（已有，强化） |
| `addWord` 入生词 | legacy.html:1610-1616 | `useVocabStore.addWord`（已有） |
| `lookupWord` | legacy.html:1572-1583 | 新加 `src/lib/dict.js` 调 `/api/dict` + 缓存 |
| `sm2` | legacy.html:1617-1622 | 旧 SM-2 不用；新用 `useVocabStore.review`（FSRS） |
| `aiSegmentFromCues` | legacy.html:1312-1556 | `src/lib/segmenter.js`（按旧版搬 + 加 `getUnderstanding`） |
| `softChunkCues` | legacy.html:1282-1310 | `src/lib/segmenter.js` |
| `exportData` / `importData` | legacy.html:2198-2217 | `src/lib/backup.js` |
| YT tick / 视频播放 | legacy.html:820-936 | 新 `src/components/VideoPlayer.jsx` |
| AI 教练 | legacy.html:2478-2607 | 新 `src/components/CoachPanel.jsx` |
| 课程库 | legacy.html:570-806 | 新 `src/pages/Course.jsx` 或合并到 `Home.jsx` |
| 转写 | legacy.html:2074-2131 | 新 `src/components/TranscribeModal.jsx` |
| 词典弹窗 | legacy.html:447-461 | 新 `src/components/DictionaryModal.jsx` |
| 语法弹窗 | legacy.html:463-476 | 新 `src/components/GrammarModal.jsx` |

---

## 7. 一次性快速复盘

- 新 app 已覆盖：三关、点词、加生词、FSRS 复习、设置基础、统计、课程库列表 & 解锁。
- 待补的真正「重活」：视频播放器（YT/本地/B 站）、导入工作流（含 AI 断句）、音频转写、词典+语法、课程下载+提交评测、AI 教练、备份、迁移、键盘。
- 体量估计：~2500–3500 行新代码，分批实现；每完成一项跑一次 `npm test` 确保不破坏现有 7 个测试文件。
