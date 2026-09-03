function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

// Minimal, safe markdown-to-HTML for the AI parse result.
// Handles: **bold** -> <b>, newlines -> <br>, "- item" -> "• item".
export function mdToHtml(md) {
  if (md == null) return ''
  return String(md)
    .split('\n')
    .map(line => {
      let s = escapeHtml(line)
      s = s.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
      s = s.replace(/^\s*-\s+/, '• ')
      return s
    })
    .join('<br>')
}
