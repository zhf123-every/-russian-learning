
/* =====================================================================
   状态管理
===================================================================== */
const LS = {
  materials:'rulearn_materials', settings:'rulearn_settings', srs:'rulearn_srs',
  dict:'rulearn_dict', session:'rulearn_session'
};
function loadLS(key, def){ try{ const v = localStorage.getItem(key); return v ? JSON.parse(v) : def; }catch(e){ return def; } }
function saveLS(key, val){ try{ localStorage.setItem(key, JSON.stringify(val)); }catch(e){} }

let state = {
  materials: loadLS(LS.materials, []),
  settings: Object.assign({baseUrl:'https://api.deepseek.com', key:'', model:'deepseek-chat'}, loadLS(LS.settings, {})),
  srs: loadLS(LS.srs, []),
  dict: loadLS(LS.dict, {}),
  session: loadLS(LS.session, {materialId:null, index:0, stage:'listen'}),
};
let current = null;   // 当前材料
let segs = [];        // 当前材料的句子数组
let curIdx = 0;       // 当前句子下标
let curStage = 'listen';
let revealed = false; // 是否已显示原文
let recognition = null;
const ytPoll = setInterval(ytTick, 300);

function persist(){ saveLS(LS.materials, state.materials); saveLS(LS.srs, state.srs); saveLS(LS.dict, state.dict); }

function toast(msg){ const t=document.getElementById('toast'); t.textContent=msg; t.classList.add('show'); clearTimeout(t._t); t._t=setTimeout(()=>t.classList.remove('show'), 2200); }

/* =====================================================================
   视频播放器
===================================================================== */
const player = {
  mode:null, yt:null, video:null, segStart:0, segEnd:0, loop:false, ready:false,
};
function ytTick(){
  if(player.mode!=='youtube' || !player.yt || !player.loop) return;
  try{
    if(player.yt.getPlayerState()===1 && player.yt.getCurrentTime() >= player.segEnd){
      player.yt.pauseVideo();   // 读完本句，停在这里
      player.loop=false;
    }
  }catch(e){}
}

function clearPlayer(){
  const wrap = document.getElementById('videoWrap');
  wrap.innerHTML = '<div class="video-placeholder">导入材料后显示视频</div>';
  player.mode=null; player.yt=null; player.video=null; player.ready=false; player.loop=false;
}
function mountYoutube(id){
  clearPlayer();
  const wrap = document.getElementById('videoWrap');
  wrap.innerHTML = '<div id="ytPlayer" style="position:absolute;inset:0"></div>';
  player.mode='youtube';
  if(window.YT && window.YT.Player){ buildYt(id); }
  else{
    window.onYouTubeIframeAPIReady = ()=>{ window.onYouTubeIframeAPIReady=null; buildYt(id); };
    const s=document.createElement('script'); s.src='https://www.youtube.com/iframe_api';
    document.head.appendChild(s);
  }
}
function buildYt(id){
  player.yt = new YT.Player('ytPlayer', {
    videoId:id, playerVars:{playsinline:1, rel:0},
    events:{ onReady:()=>{ player.ready=true; seekCurrent(); }, onStateChange:e=>{ onVideoState(e.data); } }
  });
}
async function mountLocal(blob){
  clearPlayer();
  const wrap = document.getElementById('videoWrap');
  const url = URL.createObjectURL(blob);
  const v = document.createElement('video');
  v.controls = true; v.src = url;
  v.addEventListener('timeupdate', localTick);
  v.addEventListener('ended', ()=>{ if(player.loop){ v.currentTime=player.segStart; v.play(); } });
  wrap.appendChild(v);
  player.mode='local'; player.video=v; player.ready=true;
  seekCurrent();
}
function localTick(){
  if(player.mode!=='local'||!player.video||!player.loop) return;
  if(!player.video.paused && player.video.currentTime >= player.segEnd){
    player.video.pause();   // 读完本句，停在这里
    player.loop=false;
  }
}
function onVideoState(st){
  if(player.mode==='youtube' && player.loop && st===0){ // 视频到结尾，兜底停止
    player.loop=false;
  }
}
function playSegment(start, end, loop){
  player.segStart=start; player.segEnd=end; player.loop=loop;
  seek(start); play();
}
function seek(t){
  if(player.mode==='youtube' && player.yt && player.ready){ try{ player.yt.seekTo(t,true); }catch(e){} }
  else if(player.mode==='local' && player.video){ try{ player.video.currentTime=t; }catch(e){} }
}
function play(){
  if(player.mode==='youtube' && player.yt && player.ready){ try{ player.yt.playVideo(); }catch(e){} }
  else if(player.mode==='local' && player.video){ player.video.play().catch(()=>{}); }
}
function pause(){
  if(player.mode==='youtube' && player.yt && player.ready){ try{ player.yt.pauseVideo(); }catch(e){} }
  else if(player.mode==='local' && player.video){ player.video.pause(); }
}
function seekCurrent(){ if(current && segs[curIdx]) seek(segs[curIdx].start); }

/* =====================================================================
   字幕解析
===================================================================== */
function parseTime(t){
  t=t.trim();
  let m=t.match(/(\d+):(\d{2}):(\d{2})[,.](\d{1,3})/);
  if(m) return (+m[1])*3600+(+m[2])*60+(+m[3])+(+m[4])/Math.pow(10,m[4].length);
  m=t.match(/(\d+):(\d{2})[,.](\d{1,3})/);
  if(m) return (+m[1])*60+(+m[2])+(+m[3])/Math.pow(10,m[3].length);
  return null;
}
function cleanVtt(s){ return s.replace(/<[^>]+>/g,'').replace(/\s+/g,' ').trim(); }
function parseSubtitles(text){
  const s = (text||'').replace(/\r\n/g,'\n').trim();
  const blocks = s.split(/\n{2,}/);
  const cues = [];
  for(let b of blocks){
    b=b.trim(); if(!b) continue;
    if(/^(WEBVTT|Kind:|Language:|NOTE)/i.test(b)) continue;
    const lines = b.split('\n').map(l=>l.trim()).filter(Boolean);
    const tl = lines.find(l=>l.includes('-->'));
    if(!tl) continue;
    const parts = tl.split('-->');
    const start = parseTime(parts[0]), end = parseTime(parts[1]||'');
    if(start===null) continue;
    const txt = lines.filter(l=>!l.includes('-->') && !/^\d+$/.test(l)).join(' ').trim();
    if(txt) cues.push({start, end:end===null?start+3:end, text:cleanVtt(txt)});
  }
  return cues;
}
function cuesToSentences(cues){
  // 1) 把所有 cue 拆成带时间戳的词（每条 cue 内按词数比例插值）。
  //    关键：不在 cue 边界处打断句子 —— 一个句子可以跨 cue，所以先收集词，再按标点切句。
  const words=[];
  cues.forEach(c=>{
    const ws=c.text.trim().split(/\s+/).filter(Boolean);
    if(!ws.length) return;
    const dur=c.end-c.start;
    ws.forEach((w,i)=>{ words.push({w, s:c.start+dur*(i/Math.max(1,ws.length)), e:c.start+dur*((i+1)/Math.max(1,ws.length))}); });
  });
  if(!words.length) return [];

  // 2) 按句末标点（. ! ? …）切句。标点跟在它所属的词后面；最后一个片段若无标点也独立成句。
  const out=[]; let cur=null;
  const wc=s=>s.trim().split(/\s+/).length;
  const push=()=>{ if(!cur) return; out.push({start:cur.start,end:cur.end,text:cur.text.trim()}); cur=null; };
  for(const w of words){
    const endPunct=/[.!?…]$/.test(w.w);
    if(!cur) cur={start:w.s,end:w.e,text:w.w};
    else { cur.end=w.e; cur.text+=' '+w.w; }
    if(endPunct || wc(cur.text)>=12) push();
  }
  push();
  return out;
}
function plainToSentences(text){
  const parts = text.match(/[^.!?…\n]+[.!?…]+|[^.!?…\n]+$/g);
  if(parts && parts.length>1){
    return parts.map(t=>t.trim()).filter(Boolean).map((t,i)=>({start:i*4, end:i*4+4, text:t}));
  }
  const words=(text||'').trim().split(/\s+/).filter(Boolean);
  const out=[]; const N=12;
  for(let i=0;i<words.length;i+=N) out.push({start:out.length*4, end:out.length*4+4, text:words.slice(i,i+N).join(' ')});
  return out;
}
function buildSentences(rawText){
  const cues = parseSubtitles(rawText);
  if(cues.length){ return {sentences:cuesToSentences(cues), hasTimestamps:true}; }
  return {sentences:plainToSentences(rawText), hasTimestamps:false};
}
function normalizeWord(w){ return w.toLowerCase().replace(/[.,!?…;:—«»"()'’\-]/g,''); }

let segPreviewSentences=null;
let segPreviewCues=null;
let segPreviewUnderstanding=null;

function reSegment(){
  if(!current){ toast('没有材料可断句'); return; }
  const raw=current.raw;
  if(!raw){ toast('当前材料没有原始字幕文本'); return; }
  const panel=document.getElementById('stagePanel');
  const oldHtml=panel?panel.innerHTML:'';
  if(panel){
    panel.innerHTML='<div class="row" style="flex-wrap:wrap">'
      +'<button class="btn primary" disabled>🔄 重新断句中…</button>'
      +'<button class="btn" onclick="playFull()">▶ 播放整段视频</button>'
      +'<span class="hint" style="margin:0;align-self:center">←/→ 切换，自动播放</span>'
      +'</div>'
      +'<div class="ai-loading" style="margin-top:12px">🤖 正在重新断句，请稍候…</div>';
  }
  const cues=parseSubtitles(raw);
  segPreviewCues=cues;
  if(current.hasTimestamps){
    aiSegmentFromCues(cues).then(s=>{
      if(panel) panel.innerHTML=oldHtml;
      const sentences = (s && s.length) ? s : cuesToSentences(cues);
      segPreviewUnderstanding = (s && s._understanding) ? s._understanding : null;
      segPreviewSentences=sentences;
      openSegPreview(sentences, cues);
    });
  } else {
    const sentences=plainToSentences(raw);
    segPreviewUnderstanding=null;
    segPreviewSentences=sentences;
    openSegPreview(sentences, null);
  }
}

function openSegPreview(sentences, cues){
  segPreviewSentences=sentences; segPreviewCues=cues;
  const list=document.getElementById('segPreviewList');
  const head = segPreviewUnderstanding
    ? '<div class="translation" style="margin-bottom:10px"><div class="zh-label">📖 AI 对全文的理解</div><div>'+segPreviewUnderstanding.replace(/</g,'&lt;')+'</div></div>'
    : '';
  list.innerHTML=head+sentences.map((s,i)=>'<div class="qcard" style="margin-bottom:6px">'
    +'<div class="qnum">第 '+(i+1)+' 句</div>'
    +'<div class="qtxt ru">'+s.text.replace(/</g,'&lt;')+'</div>'
    +'<div class="hint" style="font-size:11px;margin:0">⏱ '+s.start.toFixed(1)+'s – '+s.end.toFixed(1)+'s</div>'
    +'</div>').join('');
  document.getElementById('segFeedback').value='';
  openModal('modal-seg-preview');
}

function applyAISegmentation(){
  if(!segPreviewSentences || !segPreviewSentences.length){ toast('没有待应用的断句结果'); return; }
  closeModal('modal-seg-preview');
  applySegment(segPreviewSentences);
  segPreviewSentences=null; segPreviewCues=null;
}

async function regenerateWithFeedback(){
  const fb=document.getElementById('segFeedback').value.trim();
  const list=document.getElementById('segPreviewList');
  const btn=event.target.closest('button');
  if(btn){ btn.disabled=true; btn.textContent='🔄 重新生成中…'; }
  list.innerHTML='<div class="ai-loading">🤖 AI 正在根据您的意见重新断句…</div>';
  try{
    const s=await aiSegmentFromCues(segPreviewCues, fb, segPreviewSentences);
    if(s && s.length){
      segPreviewSentences=s;
      if(s._understanding) segPreviewUnderstanding=s._understanding;
      const head = segPreviewUnderstanding
        ? '<div class="translation" style="margin-bottom:10px"><div class="zh-label">📖 AI 对全文的理解</div><div>'+segPreviewUnderstanding.replace(/</g,'&lt;')+'</div></div>'
        : '';
      list.innerHTML=head+s.map((x,i)=>'<div class="qcard" style="margin-bottom:6px">'
        +'<div class="qnum">第 '+(i+1)+' 句</div>'
        +'<div class="qtxt ru">'+x.text.replace(/</g,'&lt;')+'</div>'
        +'<div class="hint" style="font-size:11px;margin:0">⏱ '+x.start.toFixed(1)+'s – '+x.end.toFixed(1)+'s</div>'
        +'</div>').join('');
      toast('已重新生成，共 '+s.length+' 句，请检查');
    } else {
      list.innerHTML='<div style="color:var(--danger)">重新生成失败，请修改意见后重试</div>';
      toast('重新生成失败');
    }
  }catch(e){
    list.innerHTML='<div style="color:var(--danger)">请求失败：'+(e.message||e)+'</div>';
  }
  if(btn){ btn.disabled=false; btn.textContent='重新生成'; }
}
function applySegment(sents){
  current.sentences=sents;
  persist();
  segs=sents;
  curIdx=Math.min(curIdx, sents.length-1);
  if(curIdx<0) curIdx=0;
  state.session.index=curIdx;
  saveLS(LS.session, state.session);
  revealed=false;
  renderSents();
  renderStudy();
  toast('已重新断句：'+sents.length+' 句');
}

function mapSentencesToCues(sentences, cues){
  // 把每个 cue 拆成 (normalized-word, start, end) 三元组数组（按词数等分时间）。
  const wordTimes=[];
  cues.forEach(c=>{
    const ws=c.text.trim().split(/\s+/).filter(Boolean);
    const dur=c.end-c.start;
    ws.forEach((w,i)=>{ wordTimes.push({w:normalizeWord(w), s:c.start+dur*(i/Math.max(1,ws.length)), e:c.start+dur*((i+1)/Math.max(1,ws.length))}); });
  });
  const out=[];
  let wi=0;
  for(const sent of sentences){
    const sw=sent.trim().split(/\s+/).map(normalizeWord).filter(Boolean);
    if(!sw.length) continue;
    let start=null, end=null;
    let matched=0;
    for(const w of sw){
      // 从 wi 起顺序找下一个完全匹配的词
      while(wi<wordTimes.length && wordTimes[wi].w!==w) wi++;
      if(wi>=wordTimes.length) break;
      if(start===null) start=wordTimes[wi].s;
      end=wordTimes[wi].e; wi++; matched++;
    }
    if(start!==null && matched===sw.length) out.push({start, end, text: sent.trim()});
  }
  return out.length>=Math.max(1, Math.floor(sentences.length*0.5)) ? out : null;
}
async function aiSegmentFromCues(cues, feedback, prevSentences){
  const s=state.settings;
  if(!s.key) return null;
  const fullText=cues.map(c=>c.text).join(' ');
  const inWords=fullText.trim().split(/\s+/).filter(Boolean);

  // 把原文分成小块，每块 3~5 个词（俄语平均句子长度），避免长文本合并
  function chunkText(text, chunkSize=4){
    const ws=text.trim().split(/\s+/).filter(Boolean);
    const out=[];
    for(let i=0;i<ws.length;i+=chunkSize) out.push(ws.slice(i,i+chunkSize).join(' '));
    return out;
  }

  // 机器校验：词数/标点/合并/顺序
  function validate(parsed, origWords){
    if(!parsed || !parsed.sentences || !parsed.sentences.length) return {ok:false, reason:'空输出'};
    const outWords=parsed.sentences.join('
    if(outSeq!==inSeq) return {ok:false, reason:'句子顺序与原文不一致'};
    return {ok:true};
  }

  const MAX_RETRIES=3;
  const sysBase = `你是俄语文本处理专家，严格按以下两步工作：

第一步：用俄语通读文本，理解内容（谁说、说什么、话题如何转换）。
第二步：基于理解，从文本开头起，遇到一个完整句子立刻断一句，继续往后读，直到文本结束。

【铁律】
1. 每句独立成一项，禁止合并两三句。
2. 禁止把一句拆成碎片（主谓语未齐就切断）。
3. 两个独立主句之间必须用句号 .，不能用逗号连接。
4. 只插入标点，不改任何词。
5. 禁止输出 markdown 标记，只返回纯净 JSON。`;

  // 带 Few-shot 示例的系统提示
  const sys = `${sysBase}

【示例】
原文：Привет как дела что нового
正确输出：{"sentences":["Привет, как дела?","Что нового?"]}
错误输出（禁止）：{"sentences":["Привет, как дела, что нового."]}
错误输出（禁止）：{"sentences":["Привет."]} {"sentences":["Как дела."]}

输出格式：
{"sentences":["Первое предложение.","Второе предложение."]}`;

  // 带反馈的系统提示（重试时用）
  function sysWithFeedback(fb, prev){
    let t=`${sysBase}\n【上一版输出有误，必须修正】\n上一版句子列表：\n`;
    if(prev && prev.length) t+=prev.map((x,i)=>`${i+1}. ${x}`).join('\n')+'\n';
    if(fb) t+=`用户反馈：${fb}\n`;
    t+=`\n请基于以上信息重新断句，保证每句独立、词数不变。输出格式：
{"sentences":["Первое предложение.","Второе предложение."]}`;
    return t;
  }

  try{
    const hasFeedback = !!(feedback && feedback.trim());
    const prevKey = (prevSentences && prevSentences.length) ? prevSentences.map(x=>x.text).join('
') : null;
    for(let attempt=0; attempt<=MAX_RETRIES; attempt++){
      const prev = (prevSentences && prevSentences.length) ? prevSentences.map(x=>x.text) : null;
      // 有反馈时：第一次也必须走反馈路径，不接受无反馈输出
      const sysMsg = (attempt===0 && !hasFeedback) ? sys : sysWithFeedback(feedback||null, prev);
      const userMsg = (attempt===0 && !hasFeedback) ? '原文（无标点）：
'+fullText : '原文（无标点）：
'+fullText+(feedback?'
用户反馈：'+feedback:'');
      const msgs=[
        {role:'system', content: sysMsg},
        {role:'user', content: userMsg}
      ];
      const content=await callAI(msgs);
      const parsed=parseAIJSON(content);
      const v=validate(parsed, inWords);
      if(v.ok){
        const mapped=mapSentencesToCues(parsed.sentences, cues);
        if(mapped){
          const newKey=parsed.sentences.join('
system',content:sys},
        {role:'user',content:'原文（无标点）：\n'+chunk}
      ]));
      if(parsed && parsed.sentences && parsed.sentences.length){
        const v=validate(parsed, chunk.trim().split(/\s+/).filter(Boolean));
        if(v.ok) allSentences.push(...parsed.sentences);
        else {
          // 单句超长 → 进一步拆分
          const sub=chunkText(chunk, 3);
          for(const sc of sub){
            const sp=parseAIJSON(await callAI([
              {role:'system',content:sys},
              {role:'user',content:'原文（无标点）：\n'+sc}
            ]));
            if(sp && sp.sentences) allSentences.push(...sp.sentences);
          }
        }
      }
    }
    if(!allSentences.length) return null;
    // 最终校验
    const finalWords=allSentences.join(' ').trim().split(/\s+/).filter(Boolean);
    if(finalWords.length!==inWords.length) return null;
    const mapped=mapSentencesToCues(allSentences, cues);
    if(mapped){ mapped._understanding=null; return mapped; }
    return null;
  }catch(e){ return null; }
}

/* =====================================================================
   点词翻译（词典）
===================================================================== */
function sentenceToHtml(text){
  const esc = text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  return esc.split(/(\s+|[.,!?…;:—\-–"«»()'’]+)/g).map(tok=>{
    if(/^\s+$/.test(tok) || /^[.,!?…;:—\-–"«»()'’]+$/.test(tok)) return tok;
    return '<span class="w" data-w="'+tok.replace(/"/g,'&quot;')+'">'+tok+'</span>';
  }).join('');
}
async function lookupWord(word){
  const w = word.replace(/^[«"'(]+|[»"').,;:!?…]+$/g,'').toLowerCase();
  const lemma = findLemma(w);
  if(lemma && RU_DICT[lemma]) return RU_DICT[lemma].z;
  if(state.dict[w]) return state.dict[w];
  try{
    const r = await fetch('/api/dict', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({word:w})});
    const j = await r.json();
    if(j.ok && j.translation){ state.dict[w]=j.translation; saveLS(LS.dict, state.dict); return j.translation; }
  }catch(e){}
  if(lemma && RU_DICT_FULL[lemma] && RU_DICT_FULL[lemma].e) return RU_DICT_FULL[lemma].e;
  return null;
}
let popEl=null;
async function openWordPop(word, x, y){
  closeWordPop();
  popEl=document.createElement('div');
  popEl.className='word-pop';
  popEl.innerHTML='<div class="w-head ru">'+word.replace(/</g,'&lt;')+'</div><div class="w-body loading">查询中…</div><div class="row"><button class="btn sm primary" onclick="addWord(\''+word.replace(/'/g,"\\'")+'\')">＋ 加入生词</button><button class="btn sm" onclick="closeWordPop()">关闭</button></div>';
  document.body.appendChild(popEl);
  const r=popEl.getBoundingClientRect();
  let px=Math.min(x, window.innerWidth-r.width-10), py=Math.min(y+12, window.innerHeight-r.height-10);
  popEl.style.left=Math.max(8,px)+'px'; popEl.style.top=Math.max(8,py)+'px';
  const body=popEl.querySelector('.w-body');
  const t=await lookupWord(word);
  body.classList.remove('loading');
  body.textContent = t || '未查到，稍后重试或点击 AI 解析';
}
function closeWordPop(){ if(popEl){ popEl.remove(); popEl=null; } }
document.addEventListener('click', e=>{
  const w=e.target.closest && e.target.closest('.w');
  if(w){ const word=w.getAttribute('data-w'); if(word){ trackLooked(word); openWordPop(word, e.clientX, e.clientY); } return; }
  if(popEl && !popEl.contains(e.target)) closeWordPop();
});

/* =====================================================================
   生词 / SM-2 间隔重复
===================================================================== */
function addWord(word){
  word=(word||'').trim();
  if(!word) return;
  if(state.srs.find(c=>c.word===word)){ toast('该词已在生词本'); closeWordPop(); return; }
  state.srs.push({word, ef:2.5, interval:0, reps:0, due:Date.now(), added:Date.now()});
  persist(); closeWordPop(); toast('已加入生词：'+word);
}
function sm2(card, q){
  if(q<3){ card.reps=0; card.interval=1; }
  else { card.interval = card.reps===0?1 : card.reps===1?6 : Math.round(card.interval*card.ef); card.reps++; }
  card.ef = Math.max(1.3, card.ef + (0.1 - (5-q)*(0.08+(5-q)*0.02)));
  card.due = Date.now() + card.interval*86400000;
}
function dueCards(){ return state.srs.filter(c=>c.due<=Date.now()); }

/* =====================================================================
   渲染：主界面
===================================================================== */
function refreshApp(){
  const has = state.materials.length>0;
  document.getElementById('view-empty').classList.toggle('hidden', has);
  document.getElementById('view-study').classList.toggle('hidden', !has);
  document.getElementById('matSelect').classList.toggle('hidden', !has);
  document.getElementById('nextMatBtn').classList.toggle('hidden', !has);
  if(!has) return;
  const sel=document.getElementById('matSelect');
  const curVal=current?current.id:(state.session.materialId||'');
  sel.innerHTML = state.materials.map(m=>'<option value="'+m.id+'">'+(m.title||'未命名材料').replace(/</g,'&lt;')+'</option>').join('');
  sel.value = curVal || state.materials[0].id;
  if(!current || current.id!==sel.value){ loadMaterial(sel.value); }
}

function onSelectMaterial(id){ state.session.materialId=id; state.session.index=0; saveLS(LS.session,state.session); loadMaterial(id); }

function loadMaterial(id){
  const m = state.materials.find(x=>x.id===id);
  if(!m) return;
  current=m; segs=m.sentences||[]; curIdx=Math.min(state.session.index||0, segs.length-1);
  curStage = state.session.stage || 'listen';
  if(curIdx<0) curIdx=0;
  resetCoach();
  // 挂视频
  if(m.type==='youtube'){ mountYoutube(m.youtubeId); }
  else if(m.type==='local'){ loadVideoBlob(m.videoBlobId).then(blob=>{ if(blob) mountLocal(blob); }); }
  renderSents();
  renderStudy();
  setStage(curStage);
}

async function loadVideoBlob(id){
  if(!id) return null;
  try{
    const db=await idb();
    return await new Promise((res,rej)=>{ const tx=db.transaction('videos','readonly'); const rq=tx.objectStore('videos').get(id); rq.onsuccess=()=>res(rq.result||null); rq.onerror=()=>rej(rq.error); });
  }catch(e){ return null; }
}
function idb(){
  return new Promise((res,rej)=>{ const r=indexedDB.open('rulearn',1);
    r.onupgradeneeded=e=>e.target.result.createObjectStore('videos');
    r.onsuccess=e=>res(e.target.result); r.onerror=e=>rej(e); });
}
async function saveVideoBlob(id, blob){
  const db=await idb();
  return new Promise((res,rej)=>{ const tx=db.transaction('videos','readwrite'); tx.objectStore('videos').put(blob,id); tx.oncomplete=res; tx.onerror=()=>rej(tx.error); });
}

function renderSents(){
  const list=document.getElementById('sentList');
  document.getElementById('sentCount').textContent = segs.length+' 句';
  list.innerHTML = segs.map((s,i)=>{
    const done = i<curIdx;
    return '<div class="sent'+(i===curIdx?' active':'')+'" onclick="goSentence('+(i-curIdx)+')">'
      +'<span class="idx">'+(i+1)+'</span>'
      +'<span class="ru">'+(done?'✓ ':'')+s.text.replace(/</g,'&lt;')+'</span></div>';
  }).join('');
  const active=list.querySelector('.sent.active');
  if(active) active.scrollIntoView({block:'nearest'});
}

function setStage(s){
  curStage=s; state.session.stage=s; saveLS(LS.session,state.session);
  document.querySelectorAll('.stage').forEach(el=>el.classList.toggle('active', el.dataset.s===s));
  renderStudy();
}

function renderStudy(){
  if(!current || !segs[curIdx]) return;
  const seg=segs[curIdx];
  const box=document.getElementById('sentenceBox');
  const panel=document.getElementById('stagePanel');
  document.getElementById('posLabel').textContent=(curIdx+1)+' / '+segs.length;
  // 原文 / 遮罩
  if(!revealed){
    box.innerHTML='<div class="cover">🙈 原文已隐藏 —— 先听</div>';
  } else {
    box.innerHTML='<div class="txt ru">'+sentenceToHtml(seg.text)+'</div>';
  }
  document.getElementById('btnReveal').textContent = revealed?'隐藏原文':'显示原文';
  // 翻译
  const tb=document.getElementById('translationBox');
  tb.classList.add('hidden');
  // 阶段面板
  if(curStage==='listen') renderListen(panel, seg);
  else if(curStage==='dictate') renderDictate(panel, seg);
  else renderRecite(panel, seg);
}

function renderListen(panel, seg){
  panel.innerHTML='<div class="row" style="flex-wrap:wrap">'
    +'<button class="btn primary" onclick="reSegment()">🔄 重新断句</button>'
    +'<button class="btn" onclick="playFull()">▶ 播放整段视频</button>'
    +'<span class="hint" style="margin:0;align-self:center">←/→ 切换，自动播放</span>'
    +'</div>';
}
function renderDictate(panel, seg){
  panel.innerHTML='<textarea class="dict-area ru" id="dictInput" placeholder="听音频，输入你听到的俄语句子…"></textarea>'
    +'<div class="row" style="margin-top:8px"><button class="btn primary" onclick="checkDictate()">检查</button>'
    +'<button class="btn" onclick="playSeg()">重听</button></div>'
    +'<div id="dictResult"></div>';
}
function renderRecite(panel, seg){
  const sup = ('SpeechRecognition' in window)||('webkitSpeechRecognition' in window);
  panel.innerHTML='<div class="row"><button class="btn primary" id="btnMic" onclick="startRecite()">🎤 开始跟读</button>'
    +'<button class="btn" onclick="toggleReveal()">'+(revealed?'隐藏':'显示')+'原文</button></div>'
    +'<div class="row" style="margin-top:8px">'
    +'<button class="btn sm" onclick="selfRate(1)">😕 不会</button>'
    +'<button class="btn sm" onclick="selfRate(2)">🙂 一般</button>'
    +'<button class="btn sm" onclick="selfRate(3)">😎 流利</button></div>'
    +'<div id="reciteResult" style="margin-top:10px"></div>';
  if(!sup) document.getElementById('btnMic').disabled=true, document.getElementById('btnMic').textContent='浏览器不支持语音识别';
}

function playSeg(){
  if(!current||!segs[curIdx]) return;
  const seg=segs[curIdx];
  playSegment(seg.start, seg.end, true);
}
function playFull(){
  if(!current) return;
  player.loop=false;
  seek(0); play();
}
function replay(){ playSeg(); }
function toggleReveal(){ revealed=!revealed; renderStudy(); }
function goSentence(d){
  const n=curIdx+d;
  if(n<0||n>=segs.length) return;
  curIdx=n; state.session.index=n; saveLS(LS.session,state.session);
  revealed=false;
  renderSents(); renderStudy();
  playSeg();
}

/* =====================================================================
   听写比对（LCS 逐字符）
===================================================================== */
function norm(s){ return s.toLowerCase().replace(/[.,!?…;:—\-–"«»()'’]/g,'').replace(/[\u0300\u0301\u0306\u0308]/g,'').replace(/\s+/g,' ').trim(); }
function lcs(a,b){
  const m=a.length,n=b.length;
  const dp=Array.from({length:m+1},()=>new Array(n+1).fill(0));
  for(let i=m-1;i>=0;i--) for(let j=n-1;j>=0;j--)
    dp[i][j]= a[i]===b[j] ? dp[i+1][j+1]+1 : Math.max(dp[i+1][j],dp[i][j+1]);
  const inRef=new Array(m).fill(false);
  let i=0,j=0;
  while(i<m&&j<n){
    if(a[i]===b[j]){ inRef[i]=true; i++; j++; }
    else if(dp[i+1][j]>=dp[i][j+1]) i++;
    else j++;
  }
  return {inRef, len:dp[0][0]};
}
function checkDictate(){
  const seg=segs[curIdx];
  const input=document.getElementById('dictInput').value;
  const ref=norm(seg.text), typ=norm(input);
  if(!typ){ toast('先输入你听到的内容'); return; }
  const {inRef,len}=lcs(ref,typ);
  const acc = ref.length? Math.round(len/ref.length*100) : 0;
  let html=''; let miss=0;
  for(let k=0;k<ref.length;k++){ if(inRef[k]) html+='<span class="ok">'+ref[k].replace(/&/g,'&amp;').replace(/</g,'&lt;')+'</span>'; else { html+='<span class="bad">'+ref[k].replace(/&/g,'&amp;').replace(/</g,'&lt;')+'</span>'; miss++; } }
  const extra = typ.length-len;
  const res=document.getElementById('dictResult');
  res.innerHTML='<div class="diff-out ru">'+html+'</div>'
    +'<div class="score">正确率 '+acc+'%'+(extra>0?' · 多打了 '+extra+' 个字符':'')+(miss>0?' · 红字是漏听/听错的': ' 🎉 完全正确！')+'</div>';
}

/* =====================================================================
   跟读（语音识别）
===================================================================== */
function startRecite(){
  const seg=segs[curIdx];
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if(!SR){ toast('浏览器不支持语音识别'); return; }
  const out=document.getElementById('reciteResult');
  out.innerHTML='<div class="ai-loading">🎤 请朗读本句…（识别中）</div>';
  const rec=new SR(); recognition=rec;
  rec.lang='ru-RU'; rec.interimResults=false; rec.maxAlternatives=1;
  rec.onresult=e=>{
    const heard=(e.results[0][0].transcript||'').trim();
    const {inRef,len}=lcs(norm(seg.text), norm(heard));
    const acc = norm(seg.text).length? Math.round(len/norm(seg.text).length*100):0;
    out.innerHTML='<div style="font-size:15px"><div class="ru" style="margin-bottom:4px">你说：'+heard.replace(/</g,'&lt;')+'</div>'
      +'<div class="score">匹配度 '+acc+'%</div></div>';
    toast('识别完成：匹配 '+acc+'%');
  };
  rec.onerror=e=>{ out.innerHTML='<div style="color:var(--danger)">识别失败：'+(e.error||'')+'。可改用「自评」按钮。</div>'; };
  rec.onend=()=>{};
  rec.start();
}
function selfRate(q){
  const out=document.getElementById('reciteResult');
  const label = q===1?'已记录：不会':q===2?'已记录：一般':'已记录：流利 👍';
  out.innerHTML='<div class="score" style="color:var(--accent)">'+label+'</div>';
  toast(label);
}

/* =====================================================================
   翻译（本句）
===================================================================== */
let transCache={};
async function toggleTranslation(){
  const tb=document.getElementById('translationBox');
  if(!tb.classList.contains('hidden')){ tb.classList.add('hidden'); return; }
  const seg=segs[curIdx];
  const key=seg.text;
  if(transCache[key]){ showTranslation(tb, transCache[key]); return; }
  tb.classList.remove('hidden');
  tb.innerHTML='<span class="zh-label">翻译中…</span>';
  try{
    const r=await fetch('/api/dict', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({word:key})});
    const j=await r.json();
    const t=(j.ok&&j.translation)?j.translation:'（翻译失败，可点「AI 解析」获取更好翻译）';
    transCache[key]=t; showTranslation(tb,t);
  }catch(e){ showTranslation(tb,'翻译失败，请确认本地服务已启动'); }
}
function showTranslation(tb,t){ tb.innerHTML='<div class="zh-label">中文翻译</div><div>'+t.replace(/</g,'&lt;')+'</div>'; }

/* =====================================================================
   AI 解析
===================================================================== */
function mdToHtml(md){
  const esc=md.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  return esc
    .replace(/^###### (.*)$/gm,'<h4>$1</h4>').replace(/^##### (.*)$/gm,'<h4>$1</h4>')
    .replace(/^#### (.*)$/gm,'<h4>$1</h4>').replace(/^### (.*)$/gm,'<h3>$1</h3>')
    .replace(/^## (.*)$/gm,'<h2>$1</h2>').replace(/^# (.*)$/gm,'<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
    .replace(/(?:^|\n)- (.*)/g,'<ul><li>$1</li></ul>')
    .replace(/\n/g,'<br>');
}
async function aiExplain(){
  const seg=segs[curIdx];
  const s=state.settings;
  if(!s.key){ toast('请先在「设置」里填写 API Key'); openSettings(); return; }
  openModal('modal-ai');
  const body=document.getElementById('aiBody');
  body.innerHTML='<div class="ai-loading">正在请 AI 老师解析…</div>';
  const messages=[
    {role:'system',content:'你是专业的俄语老师。请用中文讲解用户给出的俄语句子，输出 Markdown，包含：1) 逐词释义（每个词：俄语→中文，标注词性，动词/名词给原型）2) 语法要点 3) 整句流畅中文翻译。简洁、准确、条理清晰。'},
    {role:'user',content:'俄语句子：'+seg.text}
  ];
  try{
    const r=await fetch('/api/ai',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({baseUrl:s.baseUrl,key:s.key,model:s.model,messages})});
    const j=await r.json();
    if(!j.ok){ body.innerHTML='<div style="color:var(--danger)">'+ (j.error||'出错了').replace(/</g,'&lt;') +'</div>'; return; }
    body.innerHTML='<div class="ru" style="font-weight:600;margin-bottom:8px">'+seg.text.replace(/</g,'&lt;')+'</div>'+mdToHtml(j.content);
  }catch(e){ body.innerHTML='<div style="color:var(--danger)">请求失败：请确认本地服务已启动且网络正常。</div>'; }
}

/* =====================================================================
   导入材料
===================================================================== */
function openImport(){ resetImport(); openModal('modal-import'); }
function resetImport(){
  document.getElementById('impUrl').value=''; document.getElementById('impSubs').value='';
  document.getElementById('impTitle').value=''; document.getElementById('impFile').value='';
  document.getElementById('impType').value='youtube'; toggleImpType();
}
function toggleImpType(){
  const t=document.getElementById('impType').value;
  document.getElementById('impUrlField').classList.toggle('hidden', t!=='youtube');
  document.getElementById('impFileField').classList.toggle('hidden', t!=='local');
}
async function fetchSubs(){
  const url=document.getElementById('impUrl').value.trim();
  if(!url){ toast('先粘贴 YouTube 链接'); return; }
  const btn=document.getElementById('btnFetchSubs'); btn.disabled=true; btn.textContent='抓取中…（可能要十几秒）';
  try{
    const r=await fetch('/api/subs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
    const j=await r.json();
    if(j.ok){ document.getElementById('impSubs').value=j.text; toast('字幕抓取成功'); }
    else { alert('抓取失败：\n\n'+(j.error||'')); }
  }catch(e){ alert('请求失败：请确认本地服务已启动（python server.py）'); }
  btn.disabled=false; btn.textContent='⚡ 自动抓字幕';
}
async function saveMaterial(){
  const type=document.getElementById('impType').value;
  const url=document.getElementById('impUrl').value.trim();
  const rawText=document.getElementById('impSubs').value.trim();
  const title=document.getElementById('impTitle').value.trim();
  if(type==='youtube' && !url){ toast('请粘贴 YouTube 链接'); return; }
  if(!rawText){ toast('请粘贴字幕文本'); return; }
  const {sentences: _mech, hasTimestamps}=buildSentences(rawText);
  if(!_mech.length){ toast('字幕解析失败，请检查格式'); return; }
  let sentences=_mech;
  if(hasTimestamps && state.settings.key){
    toast('AI 正在智能断句…');
    const ai=await aiSegmentFromCues(parseSubtitles(rawText));
    if(ai && ai.length) sentences=ai;
  }
  const m={ id:'m'+Date.now().toString(36), title:title||('材料 '+(state.materials.length+1)),
    type, youtubeId:null, videoBlobId:null, raw: rawText, sentences, hasTimestamps, createdAt:Date.now() };
  if(type==='youtube'){
    const id=extractYtId(url);
    if(!id){ toast('无法识别该 YouTube 链接'); return; }
    m.youtubeId=id;
  } else {
    const file=document.getElementById('impFile').files[0];
    if(!file){ toast('请选择本地视频文件'); return; }
    m.videoBlobId='v'+Date.now().toString(36);
    await saveVideoBlob(m.videoBlobId, file);
  }
  state.materials.push(m); persist();
  state.session={materialId:m.id,index:0,stage:'listen'}; saveLS(LS.session,state.session);
  closeModal('modal-import');
  revealed=false;
  loadMaterial(m.id);
  toast('已导入 '+sentences.length+' 句，开始学习吧');
}
function extractYtId(url){
  const m=url.match(/(?:v=|youtu\.be\/|shorts\/|embed\/)([A-Za-z0-9_-]{11})/);
  return m?m[1]:null;
}
function loadDemo(){
  document.getElementById('impUrl').value='https://www.youtube.com/watch?v=dQw4w9WgXcQ';
  document.getElementById('impTitle').value='示例：俄语自我介绍';
  document.getElementById('impSubs').value =
'WEBVTT\n\n1\n00:00:01,000 --> 00:00:04,500\nПривет! Меня зовут Анна.\n\n2\n00:00:04,500 --> 00:00:08,000\nЯ из Москвы, это большой город.\n\n3\n00:00:08,000 --> 00:00:12,000\nЯ учу русский язык каждый день.\n\n4\n00:00:12,000 --> 00:00:16,000\nМне нравится читать книги и слушать музыку.\n\n5\n00:00:16,000 --> 00:00:20,000\nА что ты любишь делать?';
  toast('已填入示例字幕，可直接点「保存并开始学习」');
}

/* =====================================================================
   生词本 / 复习
===================================================================== */
function openSRS(){ openModal('modal-srs'); renderSRS(); }
function renderSRS(){
  const due=dueCards();
  document.getElementById('srsTitle').textContent='生词本（'+state.srs.length+' 个词）';
  const body=document.getElementById('srsBody');
  if(!state.srs.length){ body.innerHTML='<p style="color:var(--muted);text-align:center;padding:20px">还没有生词。学习时点单词 → 「＋ 加入生词」。</p>'; return; }
  if(due.length){
    const card=due[0];
    body.innerHTML='<div class="srs-card"><div class="q"><div class="w ru">'+card.word.replace(/</g,'&lt;')+'</div>'
      +'<div style="font-size:13px;color:var(--muted)">这个俄语词是什么意思？</div></div>'
      +'<div class="a">—— 点击下面一个按钮评级 ——</div>'
      +'<div class="srs-grades">'
      +'<button class="grade g1" onclick="rateSRS(1)">忘了</button>'
      +'<button class="grade g2" onclick="rateSRS(2)">模糊</button>'
      +'<button class="grade g3" onclick="rateSRS(3)">记得</button>'
      +'<button class="grade g4" onclick="rateSRS(4)">简单</button>'
      +'</div>'
      +'<div style="margin-top:14px"><button class="btn sm" onclick="showAnswer(\''+card.word.replace(/'/g,"\\'")+'\')">查看中文意思</button></div>'
      +'<div class="srs-stats">今天待复习 '+due.length+' 个 · 共 '+state.srs.length+' 个</div></div>';
  } else {
    body.innerHTML='<div class="srs-card"><div style="font-size:34px">🎉</div><div>今天没有到期的词，都复习完啦。</div>'
      +'<div class="srs-stats">共 '+state.srs.length+' 个生词</div></div>';
  }
}
async function showAnswer(word){
  const t=await lookupWord(word);
  const body=document.getElementById('srsBody');
  const q=body.querySelector('.q'); if(q) q.insertAdjacentHTML('afterend','<div style="font-size:17px;color:var(--accent);margin:6px 0">'+ (t||'未查到').replace(/</g,'&lt;') +'</div>');
}
function rateSRS(q){
  const card=dueCards()[0]; if(!card) return;
  sm2(card,q); persist(); renderSRS();
  toast(q<3?'会加强复习这个':'继续推进');
}

/* =====================================================================
   设置 / 备份
===================================================================== */
function openSettings(){
  document.getElementById('setBase').value=state.settings.baseUrl||'';
  document.getElementById('setKey').value=state.settings.key||'';
  document.getElementById('setModel').value=state.settings.model||'';
  openModal('modal-settings');
}
function saveSettings(){
  state.settings={ baseUrl:document.getElementById('setBase').value.trim()||'https://api.deepseek.com',
    key:document.getElementById('setKey').value.trim(), model:document.getElementById('setModel').value.trim()||'deepseek-chat' };
  saveLS(LS.settings, state.settings); closeModal('modal-settings'); toast('设置已保存');
}
function exportData(){
  const data={materials:state.materials, srs:state.srs, settings:state.settings, dict:state.dict, session:state.session};
  const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='俄语学习备份.json'; a.click(); URL.revokeObjectURL(a.href);
}
function importData(input){
  const f=input.files[0]; if(!f) return;
  const rd=new FileReader();
  rd.onload=()=>{ try{
    const d=JSON.parse(rd.result);
    if(d.materials) state.materials=d.materials;
    if(d.srs) state.srs=d.srs;
    if(d.settings) state.settings=Object.assign(state.settings,d.settings);
    if(d.dict) state.dict=d.dict;
    if(d.session) state.session=d.session;
    persist(); saveLS(LS.settings,state.settings); saveLS(LS.session,state.session);
    current=null; refreshApp(); toast('已导入备份');
  }catch(e){ alert('备份文件格式错误'); } };
  rd.readAsText(f);
}

/* =====================================================================
   弹窗 / 工具
===================================================================== */
function openModal(id){ document.getElementById(id).classList.remove('hidden'); }
function closeModal(id){ document.getElementById(id).classList.add('hidden'); }
document.querySelectorAll('.modal-mask').forEach(m=>{ m.addEventListener('click',e=>{ if(e.target===m) m.classList.add('hidden'); }); });

/* 全局：Esc 关闭弹窗、点词 */
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'){ closeWordPop(); document.querySelectorAll('.modal-mask').forEach(m=>m.classList.add('hidden')); return; }
  if(document.querySelector('.modal-mask:not(.hidden)')) return;
  const ae=document.activeElement;
  const typing = ae && (ae.tagName==='INPUT'||ae.tagName==='TEXTAREA');
  if(e.key==='ArrowRight'){ if(!typing){ e.preventDefault(); goSentence(1); } }
  else if(e.key==='ArrowLeft'){ if(!typing){ e.preventDefault(); goSentence(-1); } }
  else if(e.key===' '){ if(!typing && ae && ae.tagName!=='BUTTON'){ e.preventDefault(); replay(); } }
});

/* =====================================================================
   词典工具书（OpenRussian 开源词典，CC BY-SA 4.0）
===================================================================== */
let _DK=null;
function dictKeys(){ if(!_DK) _DK=Object.keys(window.RU_DICT_FULL||{}); return _DK; }
function openDict(){
  openModal('modal-dict');
  const q=document.getElementById('dictQuery');
  q.value=''; document.getElementById('dictResult').innerHTML='';
  setTimeout(()=>q.focus(),50);
}
function findLemma(word){
  const w=(word||'').toLowerCase().trim().replace(/^[«"'(]+|[»"').,;:!?…]+$/g,'');
  if(!w) return null;
  const F=window.RU_DICT_FULL||{}, M=window.RU_DICT||{};
  if(F[w]||M[w]) return w;
  const IRREG={буду:"быть",будешь:"быть",будет:"быть",будем:"быть",будете:"быть",будут:"быть",был:"быть",была:"быть",было:"быть",были:"быть"};
  if(IRREG[w]) return IRREG[w];
  const tryLemmas=(stem, les)=>{ for(const le of les){ const k=stem+le; if(F[k]||M[k]) return k; } return null; };
  const rules=[
    [["ами","ями","ах","ях","ам","ям","ов","ев","ёв","ей","ью","ою","ею","ой","ом","ем","ём","у","ю","а","я","ы","и","е"], ["","а","я","ый","ий","ой","ть","ить","ать","ять","еть","овать"]],
    [["ая","яя","ое","ее","ые","ие","ого","его","ому","ему","ым","им","ую","юю"], ["ый","ий","ой",""]],
    [["ит","ет","ут","ют","ат","ят"], ["ить","ать","ять","еть","овать","ть",""]],
  ];
  for(const [sufs, les] of rules){
    for(const s of sufs){
      if(w.endsWith(s) && w.length>s.length+1){
        const r=tryLemmas(w.slice(0,-s.length), les);
        if(r) return r;
      }
    }
  }
  return null;
}
function esc(s){ return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function posLabel(e){
  if(e.p==='n') return '名词'+(e.g?({m:'·阳',f:'·阴',n:'·中'}[e.g]||''):'');
  if(e.p==='v') return '动词·'+(e.asp==='p'?'完成体':'未完成体');
  if(e.p==='a') return '形容词';
  return '代词/副词等';
}
function tableHtml(head, rows){
  return '<div style="overflow-x:auto"><table class="gtable"><thead><tr>'
    +head.map(h=>'<th>'+h+'</th>').join('')+'</tr></thead><tbody>'
    +rows.map(r=>'<tr>'+r.map(c=>'<td class="ru">'+(c||'—')+'</td>').join('')+'</tr>').join('')
    +'</tbody></table></div>';
}
function nounTable(f){
  const sg=f.sg||[], pl=f.pl||[];
  return tableHtml(['格','单数','复数'],[
    ['主格',sg[0],pl[0]],['属格',sg[1],pl[1]],['与格',sg[2],pl[2]],
    ['宾格',sg[3],pl[3]],['工具格',sg[4],pl[4]],['前置格',sg[5],pl[5]]
  ]);
}
function verbTable(f){
  let html='';
  if(f.pres && f.pres.join('')) html+=tableHtml(['人称','现在/将来时'],[
    ['я 我',f.pres[0]],['ты 你',f.pres[1]],['он/она 他/她',f.pres[2]],
    ['мы 我们',f.pres[3]],['вы 你们',f.pres[4]],['они 他们',f.pres[5]]
  ]);
  if(f.past && f.past.join('')) html+=tableHtml(['过去时','形式'],[
    ['阳性',f.past[0]],['阴性',f.past[1]],['中性',f.past[2]],['复数',f.past[3]]
  ]);
  if(f.imp && (f.imp[0]||f.imp[1])) html+='<div class="gtext"><b>命令式：</b>'+(f.imp[0]||'—')+' / '+(f.imp[1]||'—')+'</div>';
  return html;
}
function adjTable(f){
  const names=['主格','属格','与格','宾格','工具格','前置格'];
  const rows=names.map((n,i)=>[n, f.m[i], f.f[i], f.n[i], f.pl[i]]);
  let html=tableHtml(['格','阳性','阴性','中性','复数'],rows);
  if(f.cmp||f.sup) html+='<div class="gtext"><b>比较级：</b>'+(f.cmp||'—')+'　<b>最高级：</b>'+(f.sup||'—')+'</div>';
  return html;
}
function renderDictEntry(lemma, e, note){
  let html='<div class="dentry">';
  html+='<div><span class="dword ru">'+esc(lemma)+'</span>';
  if(e.s && e.s!==lemma) html+=' <span class="dstress ru">'+esc(e.s)+'</span>';
  html+='<span class="dpos">'+posLabel(e)+'</span></div>';
  if(note) html+='<div class="dlemma">'+note+'</div>';
  html+='<div class="dz" id="zhslot"></div>';
  if(e.e) html+='<div class="den">'+esc(e.e)+'</div>';
  if(e.p==='v' && e.part) html+='<div class="dlemma">体配对：<b class="ru">'+esc(e.part)+'</b></div>';
  if(e.p==='n' && e.f) html+=nounTable(e.f);
  if(e.p==='v' && e.f) html+=verbTable(e.f);
  if(e.p==='a' && e.f) html+=adjTable(e.f);
  html+='</div>';
  return html;
}
function setZh(res, t){ const el=res.querySelector('#zhslot'); if(el) el.textContent=t; }
function entryFormsText(e){
  if(!e.f) return '';
  if(e.p==='n'){
    const sg=e.f.sg||[], pl=e.f.pl||[];
    const c=['主格','属格','与格','宾格','工具格','前置格'];
    return '单数：'+c.map((x,i)=>x+' '+sg[i]).join('，')+'；复数：'+c.map((x,i)=>x+' '+pl[i]).join('，');
  }
  if(e.p==='v'){
    let t='';
    if(e.f.pres && e.f.pres.join('')) t+='现在/将来时：я '+e.f.pres[0]+'，ты '+e.f.pres[1]+'，он/она '+e.f.pres[2]+'，мы '+e.f.pres[3]+'，вы '+e.f.pres[4]+'，они '+e.f.pres[5]+'；';
    if(e.f.past && e.f.past.join('')) t+='过去时：'+e.f.past[0]+'（阳）/'+e.f.past[1]+'（阴）/'+e.f.past[2]+'（中）/'+e.f.past[3]+'（复）；';
    if(e.f.imp && (e.f.imp[0]||e.f.imp[1])) t+='命令式：'+e.f.imp[0]+'/'+e.f.imp[1];
    return t;
  }
  if(e.p==='a'){
    const c=['主格','属格','与格','宾格','工具格','前置格'];
    return c.map((x,i)=>x+'：'+e.f.m[i]+'（阳）/'+e.f.f[i]+'（阴）/'+e.f.n[i]+'（中）/'+e.f.pl[i]+'（复）').join('；');
  }
  return '';
}
function aiBoxHtml(){
  return '<div style="margin-top:12px;border-top:1px solid var(--border);padding-top:12px">'
    +'<button class="btn primary sm" id="dictAiBtn">🤖 AI 助教：这是几格？为什么用这个语法？</button>'
    +'<div id="dictAiOut" style="margin-top:10px"></div></div>';
}
async function dictAI(q, lemma, e){
  const s=state.settings;
  if(!s.key){ toast('请先在「设置」里填写 API Key'); openSettings(); return; }
  const out=document.getElementById('dictAiOut');
  if(!out) return;
  out.innerHTML='<div class="ai-loading">AI 助教正在讲解…</div>';
  let userMsg='用户查的词/形式：'+q;
  if(lemma){
    userMsg+='\n原形（词典词）：'+lemma;
    if(e){ userMsg+='\n词性：'+posLabel(e); const forms=entryFormsText(e); if(forms) userMsg+='\n变格/变位表：\n'+forms; }
  }
  const messages=[
    {role:'system',content:'你是专业的俄语助教，用中文讲解。用户查词典时点你，你必须按顺序回答三点：1) 这个形式是第几格（或什么时态/人称/数/性/体）2) 为什么这里要用这个格/这个语法 3) 这个语法在什么情况下可以使用。优先结合我给的变格变位表准确判断，不要臆测。用 Markdown，简洁、直接、有条理。'},
    {role:'user',content:userMsg}
  ];
  try{
    const r=await fetch('/api/ai',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({baseUrl:s.baseUrl,key:s.key,model:s.model,messages})});
    const j=await r.json();
    if(!j.ok){ out.innerHTML='<div style="color:var(--danger)">'+(j.error||'出错了').replace(/</g,'&lt;')+'</div>'; return; }
    out.innerHTML=mdToHtml(j.content);
  }catch(err){ out.innerHTML='<div style="color:var(--danger)">请求失败：请确认本地服务已启动且网络正常。</div>'; }
}
async function dictSearch(){
  const q=document.getElementById('dictQuery').value.trim();
  const res=document.getElementById('dictResult');
  if(!q){ res.innerHTML=''; return; }
  const lemma=findLemma(q);
  if(lemma && (window.RU_DICT_FULL[lemma]||window.RU_DICT[lemma])){
    const e=window.RU_DICT_FULL[lemma];
    if(e){
      const note=(q.toLowerCase().trim()!==lemma)?'← 检测到变格/变位形式，原形为「'+lemma+'」':'';
      res.innerHTML=renderDictEntry(lemma, e, note)+aiBoxHtml();
      const zh=window.RU_DICT[lemma]?window.RU_DICT[lemma].z:null;
      if(zh){ setZh(res, zh); }
      else { setZh(res,'（中文翻译中…）'); lookupWord(lemma).then(t=>{ if(t) setZh(res,t); else setZh(res,'（无中文释义）'); }); }
      document.getElementById('dictAiBtn').addEventListener('click', ()=>dictAI(q, lemma, e));
    } else {
      const m=window.RU_DICT[lemma];
      res.innerHTML='<div class="dentry"><div><span class="dword ru">'+esc(lemma)+'</span><span class="dpos">'+m.p+'</span></div><div class="dz">'+m.z+'</div></div>'+aiBoxHtml();
      document.getElementById('dictAiBtn').addEventListener('click', ()=>dictAI(q, lemma, null));
    }
    return;
  }
  res.innerHTML='<div class="dentry"><div class="dlemma">未收录，正在联网查询…</div></div>';
  lookupWord(q).then(t=>{
    res.innerHTML='<div class="dentry"><div><span class="dword ru">'+esc(q)+'</span><span class="dpos">网络翻译</span></div><div class="dz">'+esc(t||'未查到')+'</div></div>'+aiBoxHtml();
    document.getElementById('dictAiBtn').addEventListener('click', ()=>dictAI(q, null, null));
  });
}

/* =====================================================================
   语法工具书
===================================================================== */
let grammarIdx=0;
function openGrammar(){ openModal('modal-grammar'); renderGrammar(grammarIdx); }
function renderGrammar(i){
  grammarIdx=i;
  const nav=document.getElementById('grammarNav');
  nav.innerHTML=RU_GRAMMAR.map((g,k)=>'<div class="gnav-item'+(k===i?' active':'')+'" onclick="renderGrammar('+k+')">'+g.title+'</div>').join('');
  const g=RU_GRAMMAR[i];
  const body=document.getElementById('grammarBody');
  let html=g.intro?'<div class="gintro">'+g.intro+'</div>':'';
  for(const item of g.items){
    if(item.type==='table'){
      html+='<div class="gitem"><div class="glabel">'+item.label+'</div><div style="overflow-x:auto"><table class="gtable"><thead><tr>'
        +item.head.map(h=>'<th>'+h+'</th>').join('')+'</tr></thead><tbody>'
        +item.rows.map(r=>'<tr>'+r.map(c=>'<td>'+c+'</td>').join('')+'</tr>').join('')
        +'</tbody></table></div></div>';
    } else if(item.type==='text'){
      html+='<div class="gtext">'+item.html+'</div>';
    }
  }
  body.innerHTML=html;
}
function grammarSearch(q){
  q=(q||'').trim().toLowerCase();
  const nav=document.getElementById('grammarNav');
  const body=document.getElementById('grammarBody');
  if(!q){ renderGrammar(grammarIdx); return; }
  nav.innerHTML='';
  const hits=[];
  RU_GRAMMAR.forEach((g,gi)=>{
    let ok=g.title.toLowerCase().includes(q)||(g.intro||'').toLowerCase().includes(q);
    for(const it of g.items){
      if(it.label && it.label.toLowerCase().includes(q)) ok=true;
      if(it.type==='table'){
        const all=(it.head||[]).concat((it.rows||[]).flat());
        if(all.some(c=>String(c).toLowerCase().includes(q))) ok=true;
      } else if(it.type==='text' && it.html.toLowerCase().includes(q)) ok=true;
    }
    if(ok) hits.push({gi, title:g.title});
  });
  if(!hits.length){ body.innerHTML='<div class="gintro">没有找到包含「'+q.replace(/</g,'&lt;')+'」的语法条目。</div>'; return; }
  body.innerHTML='<div class="gintro">搜索「'+q.replace(/</g,'&lt;')+'」找到 '+hits.length+' 个相关章节：</div>'
    + hits.map(h=>'<div class="gnav-item" style="border:1px solid var(--border2);padding:10px" onclick="renderGrammar('+h.gi+');document.getElementById(\'grammarSearchInput\').value=\'\'">'+h.title+'</div>').join('');
}

/* =====================================================================
   AI 学习教练
===================================================================== */
let coach={lessonId:null, phase:'idle', quiz:null, answers:[], result:null};
let lookedWords=[];

function trackLooked(word){
  word=(word||'').toLowerCase().trim().replace(/^[«"'(]+|[»"').,;:!?…]+$/g,'');
  if(!word) return;
  if(!lookedWords.includes(word)) lookedWords.push(word);
}
function resetCoach(){
  coach={lessonId:current?current.id:null, phase:'idle', quiz:null, answers:[], result:null};
  lookedWords=[];
  renderCoach();
  updateNextBtn();
}
function lessonText(){ return segs.map(s=>s.text).join('\n'); }

async function callAI(messages){
  const s=state.settings;
  const r=await fetch('/api/ai',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({baseUrl:s.baseUrl,key:s.key,model:s.model,messages})});
  const j=await r.json();
  if(!j.ok) throw new Error(j.error||'AI 接口错误');
  return j.content;
}
function parseAIJSON(content){
  let t=(content||'').trim();
  t=t.replace(/^```(?:json)?\s*/i,'').replace(/```\s*$/,'').trim();
  const a=t.indexOf('{'), b=t.lastIndexOf('}');
  if(a>=0 && b>a) t=t.slice(a,b+1);
  try{ return JSON.parse(t); }catch(e){ return null; }
}

function renderCoach(){
  const body=document.getElementById('coachBody');
  if(!body) return;
  if(coach.phase==='idle'){
    body.innerHTML='<p class="hint" style="margin:0 0 10px">完成本篇「听→听写→跟读」后做一次检测，检验是否真正掌握。已记录你本次查过的 '+lookedWords.length+' 个生词。</p>'
      +'<button class="btn primary" onclick="startCoach()">🚀 开始本篇学习检测</button>';
  } else if(coach.phase==='loading'){
    body.innerHTML='<div class="ai-loading">AI 教练正在根据课文和你的生词出题…</div>';
  } else if(coach.phase==='grading'){
    body.innerHTML='<div class="ai-loading">AI 教练正在批改你的作答…</div>';
  } else if(coach.phase==='quiz'){
    const qs=(coach.quiz&&coach.quiz.questions)||[];
    body.innerHTML=qs.map((q,i)=>{
      let input='';
      if(q.type==='choice'){
        input='<div class="qopts">'+(q.options||[]).map((o,j)=>'<label class="qopt"><input type="radio" name="q'+i+'" value="'+j+'"><span>'+esc(o)+'</span></label>').join('')+'</div>';
      } else {
        input='<input type="text" class="qfill ru" id="qf'+i+'" placeholder="用俄语作答">';
      }
      return '<div class="qcard"><div class="qnum">第 '+(i+1)+' 题 · '+(q.type==='choice'?'选择':'填空/翻译')+'</div><div class="qtxt">'+esc(q.question)+'</div>'+input+'</div>';
    }).join('')
      +'<div class="row" style="margin-top:12px"><button class="btn primary" onclick="submitCoach()">📝 提交作答</button><button class="btn" onclick="resetCoach()">重新检测</button></div>';
  } else if(coach.phase==='report'){
    body.innerHTML=renderReportHTML(coach.result);
  }
}

function renderReportHTML(r){
  if(!r) return '';
  const levelMap={pass:['✅ 通过','#16a34a'],review:['⚠️ 需复习','#d97706'],fail:['❌ 未通过','#e11d48']};
  const lm=levelMap[r.assessment_level]||['未知','#6b7280'];
  let html='<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">'
    +'<span class="level-badge" style="background:'+lm[1]+'">'+lm[0]+'</span>'
    +'<span class="score-big">'+(r.score!=null?r.score:'—')+' 分</span></div>';
  html+='<div class="rep-sec"><b>🎯 必须掌握：</b>';
  html+=(r.must_master&&r.must_master.length)?r.must_master.map(x=>'<span class="chip ru">'+esc(x)+'</span>').join(''):'<span class="hint">无</span>';
  html+='</div>';
  html+='<div class="rep-sec"><b>⚠️ 薄弱语法点：</b><ul class="rep-ul">'+((r.weak_grammar&&r.weak_grammar.length)?r.weak_grammar.map(x=>'<li>'+esc(x)+'</li>').join(''):'<li>无</li>')+'</ul></div>';
  html+='<div class="rep-sec"><b>📚 俄语学习建议：</b><ul class="rep-ul">'+((r.suggestions&&r.suggestions.length)?r.suggestions.map(x=>'<li>'+esc(x)+'</li>').join(''):'<li>—</li>')+'</ul></div>';
  html+='<div class="row" style="margin-top:12px"><button class="btn" onclick="resetCoach()">🔄 重新检测</button>';
  if(r.assessment_level==='pass') html+='<button class="btn primary" onclick="goNextMaterial()">进入下一篇 →</button>';
  else html+='<span class="hint" style="margin:0;align-self:center">⛔ 未通过检测，请复习本篇并重新检测后再进入下一篇</span>';
  html+='</div>';
  return html;
}

async function startCoach(){
  if(!segs.length){ toast('当前没有课文内容'); return; }
  const s=state.settings;
  if(!s.key){ toast('请先在「设置」里填写 API Key'); openSettings(); return; }
  coach.phase='loading'; renderCoach();
  try{
    const text=lessonText();
    const words=lookedWords.length?lookedWords.join('、'):'（本次未点击查询生词）';
    const messages=[
      {role:'system',content:'你是俄语学习教练。根据课文和学生的生词出一份检测题，检验学生是否真正掌握这篇课文。题目要覆盖：生词含义、关键语法（格/动词变位/体）、句子理解。严格只输出 JSON，不要任何解释。JSON 格式：{"questions":[{"type":"choice","question":"题目（中文，可含俄语）","options":["选项A","选项B","选项C","选项D"],"answer":"正确选项的完整内容"},{"type":"fill","question":"填空或翻译题（中文提示）","answer":"参考答案（俄语）"}]}。共 12-15 题，覆盖尽量多的知识点（生词、变格、变位、体、句子理解），难度适中偏难。'},
      {role:'user',content:'课文全文：\n'+text+'\n\n学生本次查过的生词：'+words}
    ];
    const content=await callAI(messages);
    const quiz=parseAIJSON(content);
    if(!quiz || !quiz.questions || !quiz.questions.length){ coach.phase='idle'; renderCoach(); toast('出题失败，请重试'); return; }
    coach.quiz=quiz; coach.phase='quiz'; renderCoach();
  }catch(err){ coach.phase='idle'; renderCoach(); toast('出题失败：'+(err.message||err)); }
}

async function submitCoach(){
  const qs=(coach.quiz&&coach.quiz.questions)||[];
  const answers=qs.map((q,i)=>{
    if(q.type==='choice'){
      const sel=document.querySelector('input[name="q'+i+'"]:checked');
      if(!sel) return '（未作答）';
      return q.options[parseInt(sel.value)]||'';
    }
    return (document.getElementById('qf'+i).value||'').trim()||'（未作答）';
  });
  coach.answers=answers;
  coach.phase='grading'; renderCoach();
  try{
    const messages=[
      {role:'system',content:'你是俄语学习教练。批改学生的作答，给出科学评估报告。严格只输出 JSON，不要任何解释。JSON 格式：{"assessment_level":"pass 或 review 或 fail","score":0到100的整数,"must_master":["必须掌握的生词/短语"],"weak_grammar":["薄弱语法点"],"suggestions":["具体的俄语学习建议"]}。assessment_level 判断标准（务必非常严格，宁严勿松，不要轻易给 pass）：正确率>=90% 且无任何语法/变格/变位错误=pass；60%-89% 或有一处以上错误=review；<60% 或存在严重错误=fail。'},
      {role:'user',content:'题目：'+JSON.stringify(qs)+'\n\n学生作答（与题目顺序一一对应）：'+JSON.stringify(answers)}
    ];
    const content=await callAI(messages);
    const result=parseAIJSON(content);
    if(!result){ coach.phase='quiz'; renderCoach(); toast('批改失败，请重试'); return; }
    coach.result=result; coach.phase='report'; renderCoach(); updateNextBtn();
  }catch(err){ coach.phase='quiz'; renderCoach(); toast('批改失败：'+(err.message||err)); }
}

function updateNextBtn(){
  const btn=document.getElementById('nextMatBtn');
  if(!btn) return;
  const locked = coach.result && coach.result.assessment_level!=='pass';
  btn.disabled = locked;
  btn.title = locked ? '检测未通过，请复习本篇并重新检测' : '已通过检测，进入下一篇';
  btn.style.opacity = locked ? '.45' : '';
}
function goNextMaterial(){
  if(!current) return;
  const idx=state.materials.findIndex(m=>m.id===current.id);
  if(idx<0 || idx>=state.materials.length-1){ toast('已经是最后一篇了'); return; }
  loadMaterial(state.materials[idx+1].id);
}

/* =====================================================================
   启动
===================================================================== */
refreshApp();
