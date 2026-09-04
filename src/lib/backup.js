import { LS, loadLS } from './persistence'

const ALL_KEYS = [LS.settings, LS.progress, LS.recent, LS.materials, LS.vocab, LS.session, LS.profile]

export function exportBackup() {
  const data = {}
  for (const k of ALL_KEYS) {
    data[k] = loadLS(k, null)
  }
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `russian-learning-backup-${new Date().toISOString().slice(0, 10)}.json`
  a.click()
  URL.revokeObjectURL(url)
}

export function importBackup(jsonText) {
  const data = JSON.parse(jsonText)
  for (const k of ALL_KEYS) {
    if (data[k] !== undefined) {
      localStorage.setItem(k, JSON.stringify(data[k]))
    }
  }
}