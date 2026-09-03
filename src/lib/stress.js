// 把含重音符号的俄语文本包一层 <span class="w">，重音元音包 <b class="stress">
export function renderStressed(text) {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .split(/\s+/)
    .map(w => `<span class="w">${w}</span>`)
    .join(' ')
}
