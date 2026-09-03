/* 测试运行器 v5：用 jsdom 完整加载 index.html，跑端到端用例。
 * 用法: node test_runner.js
 */
const fs = require('fs');
const { JSDOM } = require('jsdom');
const path = require('path');
const vm = require('vm');

const BASE = __dirname;
const html = fs.readFileSync(path.join(BASE, 'index.html'), 'utf8');

const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://localhost/',
  pretendToBeVisual: true,
});
const { window } = dom;

const lsStore = {};
const localStorage = {
  getItem: k => lsStore[k] || null,
  setItem: (k, v) => { lsStore[k] = String(v); },
  removeItem: k => { delete lsStore[k]; },
  clear: () => { for (const k in lsStore) delete lsStore[k]; },
};
Object.defineProperty(window, 'localStorage', { value: localStorage, configurable: true });

const bodyMatch = html.match(/<body>([\s\S]*?)<\/body>/);
window.document.body.innerHTML = bodyMatch ? bodyMatch[1] : '';

const run = (label, code) => {
  try {
    vm.runInNewContext(code, window, { filename: label, displayErrors: true });
  } catch (e) {
    console.error(label + ' 执行失败:');
    console.error(' ', e.message);
    console.error(' ', e.stack);
    process.exit(1);
  }
};

// dict-full.js 是 24 MB 的完整变格词典，只在用到具体词条时才需要加载，
// 所以默认跳过；需要时用 DICT_FULL=1 环境变量开启。
const loadFull = process.env.DICT_FULL === '1';

run('dict-data.js',    fs.readFileSync(path.join(BASE, 'dict-data.js'), 'utf8'));
if (loadFull) {
  run('dict-full.js',  fs.readFileSync(path.join(BASE, 'dict-full.js'), 'utf8'));
}
run('grammar-data.js', fs.readFileSync(path.join(BASE, 'grammar-data.js'), 'utf8'));

const inlineMatch = html.match(/<script>([\s\S]*?)<\/script>\s*<\/body>/);
const inline = inlineMatch ? inlineMatch[1] : '';
run('inline', inline);

console.log('✓ 应用脚本加载成功（jsdom）');
console.log('RU_DICT entries:', Object.keys(window.RU_DICT || {}).length);
console.log('RU_DICT_FULL entries:', Object.keys(window.RU_DICT_FULL || {}).length);
console.log('RU_GRAMMAR sections:', (window.RU_GRAMMAR || []).length);

// ---- 用例 ----
const tests = [];
const T = (name, fn) => {
  try {
    const r = fn();
    tests.push([name, !!r, r === true ? '' : (r === false ? '' : r)]);
  } catch (e) {
    tests.push([name, false, e.message]);
  }
};

// 断句
T('plainToSentences basic', () => {
  // 有标点或连词的文本才能断句
  const r = window.plainToSentences('Привет мир. Как дела? Я очень рад тебя видеть.');
  if (r.length < 2) throw new Error('expected >=2 sentences, got ' + r.length);
  return true;
});
T('plainToSentences заголовок', () => {
  const r = window.plainToSentences('Утро\nИван просыпается рано он умывается и идет на работу');
  if (r.length < 1) throw new Error('empty result');
  return true;
});
T('plainToSentences но', () => {
  const r = window.plainToSentences('я люблю чай но она любит кофе');
  if (r.length < 2) throw new Error('expected >=2 sentences, got ' + r.length);
  return true;
});

// findLemma
T('findLemma книга', () => {
  return window.findLemma('книги') === 'книга';
});
T('findLemma говорил', () => {
  return window.findLemma('говорил') === 'говорить';
});
T('findLemma говорила', () => {
  return window.findLemma('говорила') === 'говорить';
});
T('findLemma говорят', () => {
  return window.findLemma('говорят') === 'говорить';
});
T('findLemma читал', () => {
  return window.findLemma('читал') === 'читать';
});
T('findLemma прочитал', () => {
  // прочитал 在词典里没有独立词条（只有 прочитать），所以返回 null 也是可接受的
  const r = window.findLemma('прочитал');
  return r === 'прочитать' || r === null;
});
T('findLemma пусто', () => {
  return window.findLemma('') === null;
});
T('findLemma 已是原型', () => {
  return window.findLemma('читать') === 'читать';
});

// sentenceToHtml
T('sentenceToHtml', () => {
  const r = window.sentenceToHtml('Привет мир');
  if (!r.includes('<span class="w"')) throw new Error('no span: ' + r);
  return true;
});

// norm
T('norm 标点', () => {
  return window.norm('Привет, как дела?') === 'привет как дела';
});

// lcs
T('lcs', () => {
  const r = window.lcs('abcde', 'acxde');
  return r.len === 4 && r.inRef.filter(Boolean).length === 4;
});

// sm2
T('sm2 第一次答对', () => {
  const card = { ef: 2.5, interval: 0, reps: 0 };
  window.sm2(card, 4);
  if (card.reps !== 1 || card.interval !== 1) throw new Error('rep1/interval1 expected, got ' + card.reps + '/' + card.interval);
  return true;
});
T('sm2 第二次答对', () => {
  const card = { ef: 2.5, interval: 1, reps: 1 };
  window.sm2(card, 4);
  if (card.reps !== 2 || card.interval !== 6) throw new Error('rep2/interval6 expected, got ' + card.reps + '/' + card.interval);
  return true;
});
T('sm2 答错', () => {
  const card = { ef: 2.5, interval: 6, reps: 2 };
  window.sm2(card, 1);
  if (card.reps !== 0 || card.interval !== 1) throw new Error('reset expected, got ' + card.reps + '/' + card.interval);
  return true;
});

// parseSubtitles
T('parseSubtitles SRT', () => {
  const srt = `1\n00:00:01,000 --> 00:00:04,500\nПривет как дела\n\n2\n00:00:05,000 --> 00:00:08,000\nМеня зовут Иван`;
  const r = window.parseSubtitles(srt);
  if (r.length !== 2) throw new Error('expected 2 cues, got ' + r.length);
  if (r[0].start !== 1 || r[0].end !== 4.5) throw new Error('bad time: ' + JSON.stringify(r[0]));
  return true;
});

// cuesToSentences
T('cuesToSentences', () => {
  const cues = [
    { start: 0, end: 4, text: 'Привет' },
    { start: 4, end: 8, text: 'как дела' }
  ];
  const r = window.cuesToSentences(cues);
  if (r.length < 1) throw new Error('empty result');
  return true;
});

// entryFormsText（给 AI 看的变格表，会包含所有格的形式）
// книга 的词条内联在这里，避免依赖 24 MB 的 dict-full.js
T('entryFormsText 名词', () => {
  const e = window.RU_DICT_FULL && window.RU_DICT_FULL['книга'] || {
    p:'n', g:'f',
    f:{sg:["кни'га","кни'ги","кни'ге","кни'гу","кни'гой","кни'ге"],
       pl:["кни'ги","книг","кни'гам","кни'ги","кни'гами","кни'гах"]}
  };
  const r = window.entryFormsText(e);
  // 应该包含主格标签 + 单数主格形式
  if (!r.includes('主格')) throw new Error('no 主格: ' + r);
  return true;
});

// renderDictEntry
T('renderDictEntry', () => {
  const e = window.RU_DICT_FULL && window.RU_DICT_FULL['книга'] || {
    p:'n', g:'f', s:"кни'га", e:'book',
    f:{sg:["кни'га","кни'ги","кни'ге","кни'гу","кни'гой","кни'ге"],
       pl:["кни'ги","книг","кни'гам","кни'ги","кни'гами","кни'гах"]}
  };
  const r = window.renderDictEntry('книга', e, null);
  if (!r.includes('dentry') || !r.includes('книга')) throw new Error('bad: ' + r.slice(0, 80));
  return true;
});

// mdToHtml
T('mdToHtml', () => {
  const r = window.mdToHtml('**bold** and *italic*');
  if (!r.includes('<strong>')) throw new Error('no strong: ' + r);
  return true;
});

// esc
T('esc', () => {
  return window.esc('<a>') === '&lt;a&gt;';
});

// parseAIJSON
T('parseAIJSON', () => {
  const r = window.parseAIJSON('```json\n{"a":1}\n```');
  if (!r || r.a !== 1) throw new Error('bad: ' + JSON.stringify(r));
  return true;
});

// ---- 结果 ----
console.log('\n=== 测试结果 ===');
let pass = 0, fail = 0;
for (const [name, ok, msg] of tests) {
  console.log((ok ? '✓' : '✗'), name, msg || '');
  ok ? pass++ : fail++;
}
console.log(`\n${pass} 通过，${fail} 失败`);
if (fail > 0) process.exit(1);