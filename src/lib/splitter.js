export function splitText(text) {
  const raw = ((text || '').replace(/\r/g, '')
    .match(/[^.!?…]*[.!?…]+|[^.!?…]+/g) || [])
    .map(s => s.replace(/\s+/g, ' ').trim())
    .filter(Boolean)

  const out = []
  for (let i = 0; i < raw.length; i++) {
    const s = raw[i]
    const core = s.replace(/[.!?…]+$/, '')
    if (core.length < 3) {
      if (out.length) {
        out[out.length - 1] += ' ' + s
      } else if (i + 1 < raw.length) {
        raw[i + 1] = s + ' ' + raw[i + 1]
      } else {
        out.push(s)
      }
    } else {
      out.push(s)
    }
  }
  return out
}
