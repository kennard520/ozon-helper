import { describe, it, expect, vi, beforeEach } from 'vitest'
vi.mock('../auth.js', () => ({ isLoggedIn: vi.fn() }))
import { isLoggedIn } from '../auth.js'
import { router } from './index.js'

describe('router 守卫', () => {
  beforeEach(() => { vi.clearAllMocks() })
  it('未登录访问受保护路由 → 重定向 /login', async () => {
    isLoggedIn.mockReturnValue(false)
    await router.push('/stores')
    expect(router.currentRoute.value.path).toBe('/login')
  })
  it('已登录可进受保护路由', async () => {
    isLoggedIn.mockReturnValue(true)
    await router.push('/stores')
    expect(router.currentRoute.value.path).toBe('/stores')
  })
})
