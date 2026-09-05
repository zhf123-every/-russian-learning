import { create } from 'zustand'
import { loadLS, saveLS } from '../lib/persistence'

const LS_ADMIN = 'rlearn_v1_admin'

// 管理员模式：adminKey 存在即视为已登录。
// 密钥在 login() 时已通过后端 /api/admin/check 校验，之后存 localStorage 供刷新后保持。
export const useAdminStore = create((set) => ({
  adminKey: loadLS(LS_ADMIN, ''),

  async login(key) {
    const k = (key || '').trim()
    if (!k) return false
    try {
      const r = await fetch('/api/admin/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ adminKey: k }),
      })
      const j = await r.json()
      if (j.ok) {
        saveLS(LS_ADMIN, k)
        set({ adminKey: k })
        return true
      }
    } catch (e) {
      /* 后端不可用则失败 */
    }
    return false
  },

  logout() {
    saveLS(LS_ADMIN, '')
    set({ adminKey: '' })
  },
}))
