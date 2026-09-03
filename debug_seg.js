// 轻量测试：用正则从 index.html 提取 plainToSentences 函数体，直接 eval。
const fs = require('fs');
const html = fs.readFileSync('index.html', 'utf8');
const m = html.match(/function plainToSentences\(text\)\{([\s\S]*?)\nfunction buildSentences/);
const body = m[1];
const plainToSentences = new Function('text', body + '\nreturn merged.filter(s=>s.text.trim());');

const tests = [
  ['Привет как дела я очень рад тебя видеть', 2],
  ['Иван просыпается рано он умывается', 2],
  ['Я читаю книгу но она читает газету', 2],
  ['Я живу в Москве я учу русский язык', 2],
  ['Мне нравится читать и слушать музыку', 1],
  ['Утро', 1],
  ['привет', 1],
  ['Я читаю книгу', 1],
  ['Меня зовут Анна я из Москвы', 2],
  ['Привет как дела как тебя зовут', 2],
];
let allOk = true;
for (const [t, exp] of tests) {
  const r = plainToSentences(t);
  const ok = r.length >= exp;
  if (!ok) allOk = false;
  console.log(ok ? '✓' : '✗', JSON.stringify(t), '=>', r.length, 'sentences:', r.map(s => s.text));
}
process.exit(allOk ? 0 : 1);