# 音频转写（从音频断句）设计文档

日期：2026-09-03
项目：看视频学俄语（`russian-learning`）

## 1. 背景与目标

当前 App 的断句完全依赖**字幕文本**：本地视频必须先手动粘贴 SRT/VTT/纯文本字幕，才能拆成一句句台词学习。没有字幕的本地视频无法使用。

本设计新增一条「**上传视频 → 提取音频 → 语音转写 → 断句**」的流水线，让本地视频在**没有字幕**时也能通过语音识别自动生成带时间戳的台词。

### 目标（v1）
- 上传本地视频后，一键「从音频识别字幕」，自动生成 `{start, end, text}` 句子列表，直接进入现有学习流程（听 → 听写 → 跟读 → 点词翻译 → AI 解析）。
- 每句台词的播放复用现有 `<video>` seek（`playSegment(start,end)`），**不额外切音频文件**。
- 全本地、免费、无需 API Key、无需系统安装 ffmpeg。

### 非目标（v1 不做）
- 不做「提交任务 + 轮询进度」的异步转写（用户确认多数素材是短学习片段，阻塞式够用）。
- 不做每句台词的独立音频文件导出。
- 不做字幕与转写结果的对齐/融合。
- 不做除俄语外的其他语言。

## 2. 技术选型

| 环节 | 方案 | 说明 |
|------|------|------|
| 语音识别 | 本地 `faster-whisper`（CTranslate2 版 Whisper） | 离线、免费、无 key、俄语识别好、CPU 可跑 |
| 音频提取 | faster-whisper 依赖的 PyAV 直接解码视频音频轨 | **无需系统 ffmpeg**，内部完成提取 |
| 断句 | 直接采用 Whisper 的 segment（自带 start/end） | 音频时间戳即断句依据，**不用 razdel** |
| 每句播放 | 复用现有 `playSegment(start,end)` seek | 零额外存储 |
| 默认模型 | `small`（约 460MB） | 俄语质量/速度平衡；可在设置切换 |

## 3. 架构

```
前端 index.html                        后端 server.py
─────────────────                      ──────────────────
[导入弹窗·本地视频]                     POST /api/transcribe
  └ 🎙 从音频识别字幕                     ├ 流式接收视频原始字节 → 临时文件
      └ fetch(文件体) ────────────────►  ├ faster-whisper 转写(ru, word_timestamps)
        ◄── {segments:[{start,end,text}]} └ 返回 JSON
  └ 预览句子 → 保存 material
      (videoBlob 存 IndexedDB + 带时间戳句子)
```

## 4. 后端设计（server.py）

### 4.1 新端点 `POST /api/transcribe`

- **请求**：原始二进制体（非 multipart），`Content-Type` 为视频类型；文件名经 query 传 `?name=<urlencoded>` 以保留扩展名（供 PyAV 识别容器）。
- **接收**：新增 `_read_raw_to_file()`，按 1MB 分块把 `self.rfile` 流式写入 `tempfile.mkdtemp` 下的临时文件，避免大文件占满内存。
- **处理**：`transcribe_file(tmp_path)` → 返回 `[ {start, end, text}, ... ]`。
- **响应**：
  - 成功：`{ "ok": true, "segments": [ {start, end, text}, ... ] }`
  - 失败：`{ "ok": false, "error": "可读错误信息" }`

### 4.2 模型懒加载 + 单例缓存

仿照现有 `razdel` 的懒加载写法：

```python
try:
    from faster_whisper import WhisperModel
    _WHISPER_OK = True
except Exception:
    _WHISPER_OK = False

_whisper_model = None
_whisper_model_name = None

def get_whisper_model(name):
    global _whisper_model, _whisper_model_name
    if _whisper_model is None or _whisper_model_name != name:
        _whisper_model = WhisperModel(name, device="cpu", compute_type="int8")
        _whisper_model_name = name
    return _whisper_model
```

模型只加载一次，之后复用；切换模型名时重新加载。

### 4.3 转写逻辑 `transcribe_file`

```python
def transcribe_file(path, model_name="small"):
    if not _WHISPER_OK:
        return None, "未安装 faster-whisper。请运行：python -m pip install faster-whisper"
    model = get_whisper_model(model_name)
    segments, info = model.transcribe(
        path, language="ru", word_timestamps=True, vad_filter=True
    )
    out = []
    for s in segments:
        t = s.text.strip()
        if not t:
            continue
        out.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": t})
    if not out:
        return [], "未识别到俄语语音（可能没有音频轨，或内容非俄语）"
    out = _merge_tiny_segments(out)   # 轻量清理，见 4.4
    return out, None
```

- `vad_filter=True`：用内置 VAD 裁掉首尾静音，让时间戳更贴合实际语音，段界更干净。
- `compute_type="int8"`：CPU 上提速。
- 转写在 `ThreadingHTTPServer` 的请求线程内**同步阻塞**执行，不阻塞其他请求。

### 4.4 轻量清理 `_merge_tiny_segments`

Whisper 偶发切出极短碎片（如单个"Да"、"Ну"或标点残片）。规则：若某段文本（去空格）少于 3 字符且与前后段间隔 < 0.5s，合并到相邻段（时间戳取并集）。其余保持 Whisper 原样，**不做 razdel 二次切分**。

## 5. 前端设计（index.html）

### 5.1 新增按钮与流程

- 「导入材料」弹窗中，`impType === 'local'` 时在文件选择框下方显示按钮 `🎙 从音频识别字幕`（本地类型专用）。
- 点击触发 `transcribeAudio()`：
  1. 取 `impFile.files[0]`，为空则 toast 提示先选文件。
  2. 按钮禁用、文案改为「🎙 转写中…（可能要几分钟）」，弹层内显示加载态。
  3. `fetch('/api/transcribe?name=' + encodeURIComponent(file.name), { method:'POST', body:file })`。
  4. 成功后把 `j.segments` 存到临时变量，弹出**转写预览**（见 5.2）。
  5. 失败：`alert('识别失败：\n\n' + j.error)`，按钮恢复。

### 5.2 转写预览（轻量）

复用现有弹层样式，新建一个 `modal-transcribe`（或复用 `segPreview` 结构）：列出每句序号 + 俄语原文 + 时间戳 `⏱ x.xs – y.ys`，底部「✅ 保存并开始学习」按钮。

- 保存时构造 material：`{ id, title, type:'local', videoBlobId, raw:'', sentences, hasTimestamps:true, createdAt }`，`saveVideoBlob()` 存视频到 IndexedDB，`pushMaterial()` 进入学习。
- **不经过** `saveMaterial()`（那条路强制要求 `rawText`），`raw` 留空。

### 5.3 设置项

「设置」弹窗新增 Whisper 模型下拉：`tiny / base / small / medium`（默认 `small`），存 `state.settings.whisperModel`，转写时经 query 或 JSON 传给后端。

> 注：上传文件体与模型名需同传。采用 query 传 `name` + `model`，body 传文件字节，避免 multipart。

## 6. 依赖与运行环境

- `python -m pip install faster-whisper`（自动带 `ctranslate2`、`av`、`tokenizers`、`onnxruntime`、`huggingface_hub`）。
- 模型首次使用自动从 HuggingFace 下载到缓存目录；国内网络可设 `HF_ENDPOINT=https://hf-mirror.com`。
- **Python 3.14 wheel 风险**：系统默认 Python 3.14，`ctranslate2` / `av` 可能尚无 cp314 预编译 wheel。**兜底**：用机器上已有的 Python 3.11.15（`gpt_academic\.venv` 的运行时）为本项目新建独立 `.venv`，`server.py` 及 `启动.bat` 改为用该 venv 的 python 启动。

## 7. 错误处理

| 场景 | 处理 |
|------|------|
| 未安装 faster-whisper | 后端返回「请运行 pip install faster-whisper」，前端 alert 展示 |
| 视频无音频轨 / 非俄语 / 识别为空 | 后端返回明确错误，前端 alert |
| 模型首次下载失败（网络） | 异常捕获，返回可读错误；提示可切 hf-mirror 镜像 |
| 转写中途异常 | 后端 500 返回 `str(e)`，前端 alert，按钮恢复，可回退手动粘字幕 |
| 临时文件 | `finally` 中 `shutil.rmtree` 清理 |

## 8. 测试

1. **后端单测/脚本**：用一段俄语音频调用 `transcribe_file`，断言返回 list、每项含 `start/end/text` 且 `end > start`、时间戳单调递增。
2. **格式验证**：返回的句子能被现有 `playSegment(start,end)` 正确 seek。
3. **手动全流程**：上传本地俄语视频 → 「从音频识别」→ 预览 → 保存 → 逐句「听/听写/跟读」正常、时间戳对齐。
4. **异常路径**：无音频轨视频、未装 faster-whisper、网络不通，均给出可读提示而非崩溃。

## 9. 实现顺序

1. 后端：新增 `/api/transcribe` + `transcribe_file` + 模型懒加载 + 原始字节流式接收 + 清理。
2. 依赖：安装 faster-whisper（如 3.14 无 wheel，建 3.11 venv）。
3. 前端：导入弹窗加按钮 + 转写预览 + 设置项 + 保存流程。
4. 联调：走通全流程 + 异常路径。
