// 通用 AI 中转：由后端持有密钥，前端不再直接调用第三方 AI 接口
export async function chat({ messages } = {}) {
  const r = await fetch('/api/ai', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }),
  })
  const j = await r.json()
  if (!j.ok) throw new Error(j.error || 'AI 接口错误')
  return j.content
}

// 调用后端 /api/ai（统一 AI 入口，密钥在服务端环境变量中）
export async function callAI(messages) {
  const r = await fetch('/api/ai', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages })
  })
  const j = await r.json()
  if (!j.ok) throw new Error(j.error || 'AI 接口错误')
  return j.content
}

// 解析 AI 返回的 JSON（去除 markdown 代码块包裹）
export function parseAIJSON(content) {
  let t = (content || '').trim()
  // 去掉 ```json ... ``` 包裹
  t = t.replace(/^```(?:json)?\s*/i, '').replace(/```\s*$/, '').trim()
  // 提取 { ... }
  const a = t.indexOf('{'), b = t.lastIndexOf('}')
  if (a >= 0 && b > a) t = t.slice(a, b + 1)
  try {
    return JSON.parse(t)
  } catch (e) {
    return null
  }
}

// 语法解释：调用后端 /api/grammar（服务端持有密钥）
export async function explainSentence(text) {
  const r = await fetch('/api/grammar', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sentence: text }),
  })
  const j = await r.json()
  if (!j.ok) throw new Error(j.error || '语法解析失败')
  return j.content
}
