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
    if (/^(чтобы|если|когда|хотя|потому|поэтому|так как|перед тем как|после того как)$/.test(low) && cur.length >= 2) return true;
    if (/^(что|как|где|почему|зачем|куда|ли|разве|неужели)$/.test(low) && cur.length >= 2) return true;
    if (/^(да|нет|ну|ладно|хорошо|давай|пожалуйста|вот)$/.test(low) && cur.length >= 1) return true;
    if (/^(я|ты|мы|вы|они|он|она|оно)$/.test(low) && next) {
      const nl = next.toLowerCase();
      if (/(ет|ют|ю|ёшь|ёте|ешь|ете|ется|ются|ал|ла|ло|ли|ть|ти|лся|лась|лось|лись)$/i.test(nl)) return true;
    }
    return false;
  };
  const MAXW = 18;
  for(let i=0; i<words.length; i++){
    const w = words[i];
    const next = words[i+1];
    cur.push(w);
    let shouldCut = false;
    if(isEndWord(w)) shouldCut = true;
    else if(cur.length >= MAXW) shouldCut = true;
    else if(i > 0 && isClauseStart(w, next) && cur.length >= 2) shouldCut = true;
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

// Test 1: Title + body no punctuation
const text1 = "Утро\nИван просыпается в 6:00 утра он видит восход солнца";
console.log("=== Test 1: Title + body no punctuation ===");
const s1 = plainToSentences(text1);
console.log("Sentences:", s1.length);
s1.forEach((s,i) => console.log(`  ${i+1}. ${s.text}`));

// Test 2: Body only no title
const text3 = "Иван просыпается в 6:00 утра он видит восход солнца";
console.log("\n=== Test 2: Body only no punctuation ===");
const s3 = plainToSentences(text3);
console.log("Sentences:", s3.length);
s3.forEach((s,i) => console.log(`  ${i+1}. ${s.text}`));

// Test 3: With "он" clause start
const text5 = "Иван просыпается в 6:00 утра он видит восход солнца он идет на работу";
console.log("\n=== Test 3: With 'он' clause start ===");
const s5 = plainToSentences(text5);
console.log("Sentences:", s5.length);
s5.forEach((s,i) => console.log(`  ${i+1}. ${s.text}`));

// Test 4: Multiple subjects with "и"
const text6 = "Иван и Маша идут в школу они учатся там каждый день я люблю читать книги";
console.log("\n=== Test 4: Multiple subjects with 'и' ===");
const s6 = plainToSentences(text6);
console.log("Sentences:", s6.length);
s6.forEach((s,i) => console.log(`  ${i+1}. ${s.text}`));

// Test 5: With "а" (but) - common conjunction
const text7 = "я люблю чай а она любит кофе мы пьем каждый день";
console.log("\n=== Test 5: With 'а' (but) ===");
const s7 = plainToSentences(text7);
console.log("Sentences:", s7.length);
s7.forEach((s,i) => console.log(`  ${i+1}. ${s.text}`));
