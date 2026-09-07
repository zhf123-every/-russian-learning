// 视频播放控制层
//
// 目标：让「按句子时间点精确跳转 / 循环 / 变速」对用户来说是同一个操作，
//       而不是依赖浏览器原生控件。
//
// 两种播放载体：
//   - direct（mp4 直链 / 仓库路径）：用 <video> 元素，可精确 seek / playbackRate / 循环
//   - youtube / bilibili（iframe 嵌入）：用 postMessage 尽力控制，精度受限
//
// 对 direct：segStart/segEnd 严格对齐，循环时 currentTime >= segEnd 立即跳回 segStart。
// 对 iframe：只在「单句播放」时尽力跳到 segStart，循环用定时器近似。

export function getVideoPlay(url) {
  if (!url) return null
  const m = url.match(/(?:v=|youtu\.be\/|shorts\/|embed\/)([A-Za-z0-9_-]{11})/)
  if (m) return { type: 'youtube', src: 'https://www.youtube.com/embed/' + m[1] + '?enablejsapi=1&origin=' + (typeof location !== 'undefined' ? location.origin : '') }
  const bv = url.match(/BV[0-9A-Za-z]{10}/)
  if (bv) return { type: 'bilibili', src: 'https://player.bilibili.com/player.html?bvid=' + bv[0] + '&autoplay=0' }
  return { type: 'direct', src: url }
}

// 建立一个播放器句柄。videoEl 是 <video> 元素的 ref（仅 direct 类型需要）。
// 返回的 handle 对 direct / iframe 都有相同的方法名，调用方无需区分。
export function createPlayer(play, videoEl) {
  const h = {
    type: play ? play.type : null,
    src: play ? play.src : null,
    videoEl,
    segStart: 0,
    segEnd: 0,
    loop: false,
    loopContinuous: false,
    rate: 1.0,
    playing: false,
    _timer: null,
  }

  // ---- direct：精确控制 ----
  function directSeek(t) {
    if (!h.videoEl) return
    try { h.videoEl.currentTime = t } catch (e) {}
  }
  function directPlay() {
    if (!h.videoEl) return
    h.videoEl.playbackRate = h.rate
    h.videoEl.play().catch(() => {})
    h.playing = true
  }
  function directPause() {
    if (!h.videoEl) return
    h.videoEl.pause()
    h.playing = false
  }
  function directTick() {
    if (!h.videoEl) return
    const v = h.videoEl
    if (v.ended) { h.playing = false; return }
    if (h.loopContinuous && v.currentTime >= h.segEnd - 0.05) {
      try { v.currentTime = h.segStart } catch (e) {}
    } else if (h.loop && v.currentTime >= h.segEnd - 0.05) {
      v.pause()
      h.playing = false
      try { v.currentTime = h.segStart } catch (e) {}
    }
  }

  // ---- iframe：尽力控制 ----
  function iframePost(msg) {
    if (!h._iframe) return
    try { h._iframe.contentWindow.postMessage(JSON.stringify(msg), '*') } catch (e) {}
  }
  function iframeSeek(t) {
    iframePost({ method: 'seekTo', time: t })
  }
  function iframePlay() {
    iframePost({ method: 'playVideo' })
    h.playing = true
  }
  function iframePause() {
    iframePost({ method: 'pauseVideo' })
    h.playing = false
  }
  function iframeTick() {
    // 循环用定时器近似；YouTube 拿不到精确 currentTime，尽力而为
    if (!h.loopContinuous || !h.playing) return
    if (h._timer) clearTimeout(h._timer)
    const dur = Math.max(0.1, (h.segEnd - h.segStart))
    h._timer = setTimeout(() => {
      if (h.loopContinuous && h.playing) {
        iframeSeek(h.segStart)
        iframePlay()
      }
    }, dur * 1000 * h.rate)
  }

  h._tick = h.type === 'direct' ? directTick : iframeTick
  h._seek = h.type === 'direct' ? directSeek : iframeSeek
  h._play = h.type === 'direct' ? directPlay : iframePlay
  h._pause = h.type === 'direct' ? directPause : iframePause

  // 绑定 <video> 的 timeupdate（仅 direct）
  if (h.type === 'direct' && h.videoEl) {
    h.videoEl.addEventListener('timeupdate', () => h._tick())
    h.videoEl.addEventListener('ended', () => { h.playing = false })
  }

  h.setRate = (r) => {
    h.rate = r
    if (h.type === 'direct' && h.videoEl) {
      try { h.videoEl.playbackRate = r } catch (e) {}
    } else if (h.type === 'youtube') {
      iframePost({ method: 'setPlaybackRate', rate: r })
    }
  }
  h.seek = (t) => { h._seek(t) }
  h.play = () => { h._play() }
  h.pause = () => { h._pause() }
  h.playSegment = (start, end, loop = true) => {
    h.segStart = start
    h.segEnd = end
    h.loop = loop
    h.loopContinuous = false
    if (h._timer) { clearTimeout(h._timer); h._timer = null }
    h.seek(start)
    h.play()
  }
  h.playLoop = (start, end) => {
    h.segStart = start
    h.segEnd = end
    h.loop = true
    h.loopContinuous = true
    if (h._timer) { clearTimeout(h._timer); h._timer = null }
    h.seek(start)
    h.play()
    h._tick()
  }
  h.stopLoop = () => {
    h.loop = false
    h.loopContinuous = false
    if (h._timer) { clearTimeout(h._timer); h._timer = null }
  }
  h.getCurrentTime = () => {
    if (h.type === 'direct' && h.videoEl) {
      try { return h.videoEl.currentTime } catch (e) { return 0 }
    }
    return 0
  }
  h.playFull = () => {
    h.loop = false
    h.loopContinuous = false
    if (h._timer) { clearTimeout(h._timer); h._timer = null }
    h.seek(0)
    h.play()
  }
  h.setIframe = (el) => { h._iframe = el }

  return h
}