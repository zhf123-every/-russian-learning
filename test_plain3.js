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
  const isClauseStart = (w) => {
    const low = w.toLowerCase();
    return /^(и|но|а|или|зато|однако|потому|чтобы|если|когда|хотя|что|как|где|почему|зачем|куда|да|нет|ну|ладно|хорошо|давай|пожалуйста|вот|всё|это|он|она|оно|мы|вы|они|я|ты)\b/.test(low);
  };
  const isVerbEnding = (w) => /(ется|ются|ется|ут|ют|ешь|ете|ет|ю|ёшь|ёте|ал|ла|ло|ли|ть|ти|ться)$/i.test(w);
  const MAXW = 18;
  for(let i=0; i<words.length; i++){
    const w = words[i];
    cur.push(w);
    let shouldCut = false;
    if(isEndWord(w)) shouldCut = true;
    else if(cur.length >= MAXW) shouldCut = true;
    else if(i > 0 && isClauseStart(w) && cur.length >= 3) shouldCut = true;
    else if(i > 0 && isVerbEnding(w) && cur.length >= 4) shouldCut = true;
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

// Test 2: Title + body with punctuation
const text2 = "Утро\nИван просыпается в 6:00 утра. Он видит восход солнца.";
console.log("\n=== Test 2: Title + body with punctuation ===");
const s2 = plainToSentences(text2);
console.log("Sentences:", s2.length);
s2.forEach((s,i) => console.log(`  ${i+1}. ${s.text}`));

// Test 3: Just body no title
const text3 = "Иван просыпается в 6:00 утра он видит восход солнца";
console.log("\n=== Test 3: Body only no punctuation ===");
const s3 = plainToSentences(text3);
console.log("Sentences:", s3.length);
s3.forEach((s,i) => console.log(`  ${i+1}. ${s.text}`));

// Test 4: Long body
const text4 = "Иван просыпается в 6:00 утра он видит восход солнца идет на работу встречает друга они вместе пьют кофе обсуждают планы на день потом идут в офис";
console.log("\n=== Test 4: Long body, no punctuation ===");
const s4 = plainToSentences(text4);
console.log("Sentences:", s4.length);
s4.forEach((s,i) => console.log(`  ${i+1}. ${s.text}`));

// Test 5: With "он" clause start
const text5 = "Иван просыпается в 6:00 утра он видит восход солнца он идет на работу";
console.log("\n=== Test 5: With 'он' clause start ===");
const s5 = plainToSentences(text5);
console.log("Sentences:", s5.length);
s5.forEach((s,i) => console.log(`  ${i+1}. ${s.text}`));
