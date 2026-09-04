function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

// 简易、安全的 markdown → HTML（AI 解析结果用）。
// 支持：标题（# / ## / ###）、代码块（``` ... ```）、**加粗**、行内 `code`、列表（- 或 *）、有序列表（1. 2.）、引用（>）
export function mdToHtml(md) {
  if (md == null) return ''
  const src = String(md).split('\n')
  const out = []
  let inCodeBlock = false
  let codeBuffer = []

  for (let i = 0; i < src.length; i++) {
    const raw = src[i]
    const trimmed = raw.trim()

    // 代码块开始/结束
    if (trimmed.startsWith('```')) {
      if (!inCodeBlock) {
        inCodeBlock = true
        codeBuffer = []
      } else {
        out.push(`<pre><code>${escapeHtml(codeBuffer.join('\n'))}</code></pre>`)
        inCodeBlock = false
        codeBuffer = []
      }
      continue
    }
    if (inCodeBlock) {
      codeBuffer.push(raw)
      continue
    }

    // 标题
    if (/^###\s/.test(trimmed)) {
      out.push(`<h3>${escapeHtml(trimmed.slice(4))}</h3>`)
      continue
    }
    if (/^##\s/.test(trimmed)) {
      out.push(`<h2>${escapeHtml(trimmed.slice(3))}</h2>`)
      continue
    }
    if (/^#\s/.test(trimmed)) {
      out.push(`<h1>${escapeHtml(trimmed.slice(2))}</h1>`)
      continue
    }

    // 引用
    if (/^>\s/.test(trimmed)) {
      out.push(`<blockquote>${escapeHtml(trimmed.slice(2))}</blockquote>`)
      continue
    }

    // 有序列表
    if (/^\d+\.\s/.test(trimmed)) {
      out.push(`<ol><li>${escapeHtml(trimmed.replace(/^\d+\.\s/, ''))}</li></ol>`)
      continue
    }

    // 无序列表（含缩进嵌套）
    const indentMatch = raw.match(/^(\s*)[-*]\s(.+)$/)
    if (indentMatch) {
      const indent = indentMatch[1].length
      const content = formatInline(escapeHtml(indentMatch[2]))
      const style = indent ? ` style="margin-left:${indent * 2}em"` : ''
      out.push(`<ul><li${style}>${content}</li></ul>`)
      continue
    }

    // 行内代码
    let s = escapeHtml(raw)
    s = formatInline(s)

    out.push(s)
  }

  // 行尾漏闭合的代码块也输出
  if (inCodeBlock && codeBuffer.length) {
    out.push(`<pre><code>${escapeHtml(codeBuffer.join('\n'))}</code></pre>`)
  }

  return out.join('<br>')
}

// 内联格式化：代码、加粗、斜体
function formatInline(s) {
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>')
  s = s.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
  s = s.replace(/(^|[^*])\*([^*]+)\*([^*]|$)/g, '$1<i>$2</i>$3')
  return s
}