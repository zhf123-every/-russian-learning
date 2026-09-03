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

export async function explainSentence(text, settings) {
  return chat({
    ...settings,
    messages: [
      { role: 'system', content: '你是俄语老师。逐词解析这句俄语：原形、词性、语法功能、整句中文翻译。用简洁中文，适当用列表。' },
      { role: 'user', content: text },
    ],
  })
}
