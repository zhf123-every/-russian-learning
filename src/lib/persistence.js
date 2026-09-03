export const LS = {
  progress: 'rlearn_v1_progress',
  vocab: 'rlearn_v1_vocab',
  recent: 'rlearn_v1_recent',
  materials: 'rlearn_v1_materials',
  settings: 'rlearn_v1_settings',
}

export function loadLS(key, def) {
  try { const v = localStorage.getItem(key); return v == null ? def : JSON.parse(v) }
  catch (e) { return def }
}

export function saveLS(key, val) {
  try { localStorage.setItem(key, JSON.stringify(val)) }
  catch (e) { /* 忽略：配额满/隐私模式 */ }
}
