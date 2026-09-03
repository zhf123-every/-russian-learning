function plainToSentences(text){
  const lines = (text||'').trim().split('\n').map(l=>l.trim()).filter(Boolean);
  const filtered = lines.filter(l => {
    const words = l.split(/\s+/).filter(Boolean);
    if (words.length < 4 && lines.indexOf(l) !== lines.length - 1) return false;
    return true;
  });
  const cleaned = filtered.join(' ');
  const parts = cleaned.match(/[^.!?…\n]+[.!?…]+|[^.!?…\n]+$/g);
  if(parts && parts.length>1){
    return parts.map(t=>t.trim()).filter(Boolean).map((t,i)=>({start:i*4, end:i*4+4, text:t}));
  }
  const words = cleaned.trim().split(/\s+/).filter(Boolean);
  if(words.length <= 1) return words.map(w=>({start:0, end:4, text:w}));
  const out=[]; let cur=[];
  const isEndWord = (w) => /[.!?…]$/.test(w);
  const isClauseStart = (w, next) => {
    const low = w.toLowerCase();
    if (/^(что|как|где|почему|зачем|куда|ли|разве|неужели)$/.test(low)) return true;
    if (/^(да|нет|ну|ладно|хорошо|давай|пожалуйста|вот)$/.test(low)) return true;
    if (/^(я|ты|мы|вы|они|он|она|оно)$/.test(low) && next) {
      const nl = next.toLowerCase();
      if (/(ет|ют|ю|ёшь|ёте|ешь|ете|ется|ются|ал|ла|ло|ли|ть|ти|лся|лась|лось|ались)$/i.test(nl)) return true;
    }
    if (/^(но|однако|зато)$/.test(low)) return true;
    if (/^(чтобы|если|когда|хотя|потому|поэтому|так как|перед тем как|после того как)$/.test(low)) return true;
    return false;
  };
  const MAXW = 18;
  for(let i=0; i<words.length; i++){
    const w = words[i];
    const next = words[i+1];
    const atNewStart = (i > 0 && cur.length >= 2 && isClauseStart(w, next));
    if(atNewStart){
      out.push({start: out.length * 4, end: out.length * 4 + 4, text: cur.join(' ')});
      cur = [];
    }
    cur.push(w);
    let shouldCut = false;
    if(isEndWord(w)) shouldCut = true;
    else if(cur.length >= MAXW) shouldCut = true;
    if(shouldCut){
      out.push({start: out.length * 4, end: out.length * 4 + 4, text: cur.join(' ')});
      cur = [];
    }
  }
  if(cur.length) out.push({start: out.length * 4, end: out.length * 4 + 4, text: cur.join(' ')});
  const merged=[];
  for(const s of out){
    const wc2 = s.text.trim().split(/\s+/).filter(Boolean).length;
    if(wc2 < 2 && merged.length){
      const p = merged[merged.length-1];
      p.text = (p.text + ' ' + s.text).trim();
      p.end = s.end;
    } else merged.push(s);
  }
  return merged.filter(s=>s.text.trim());
}

const tests = [
  ["Title + body", "Утро\nИван просыпается в 6:00 утра он видит восход солнца он идет на работу"],
  ["With но (but)", "я люблю чай но она любит кофе мы пьем каждый день"],
  ["Multiple subjects", "Иван и Маша идут в школу они учатся там каждый день я люблю читать книги"],
  ["Long text", "Иван просыпается в 6:00 утра он видит восход солнца идет на работу встречает друга они вместе пьют кофе обсуждают планы потом идут в офис"],
  ["No subject pronouns", "Иван просыпается рано утром он умывается и идет на работу"],
];

tests.forEach(([name, text]) => {
  console.log(`\n=== ${name} ===`);
  const s = plainToSentences(text);
  console.log(`Sentences: ${s.length}`);
  s.forEach((s,i) => console.log(`  ${i+1}. ${s.text}`));
});
