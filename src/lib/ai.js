export async function chat({ baseUrl, apiKey, model, messages }) {
  if (!apiKey) throw new Error('未配置 API Key，请在设置里填写')
  const res = await fetch((baseUrl.replace(/\/$/, '') + '/chat/completions'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + apiKey },
    body: JSON.stringify({ model, messages, temperature: 0.3 }),
  })
  if (!res.ok) {
    const t = await res.text().catch(() => '')
    throw new Error('请求失败 ' + res.status + (t ? ': ' + t.slice(0, 200) : ''))
  }
  const j = await res.json()
  return j.choices?.[0]?.message?.content || ''
}

// 调用后端 /api/ai（统一 AI 入口，由后端转发到实际模型）
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

export async function explainSentence(text, settings) {
  return chat({
    ...settings,
    messages: [
      { role: 'system', content: '你是俄语老师。逐词解析这句俄语：原形、词性、语法功能、整句中文翻译。用简洁中文，适当用列表。' },
      { role: 'user', content: text },
    ],
  })
}