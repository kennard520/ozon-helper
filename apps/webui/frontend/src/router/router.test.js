import { describe, it, expect, vi, beforeEach } from 'vitest'
vi.mock('../auth.js', () => ({ isLoggedIn: vi.fn() }))
import { isLoggedIn } from '../auth.js'
import { router } from './index.js'
import { createPinia, setActivePinia } from 'pinia'
import { useAppStore } from '../stores/app.js'

describe('router 守卫', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
    useAppStore().runtimeLoaded = true
  })
  it('本地模式直接访问运营页面回到工作台', async () => {
    isLoggedIn.mockReturnValue(true)
    useAppStore().runtime = { local_lite: true }
    await router.push('/wallet')
    expect(router.currentRoute.value.path).toBe('/')
  })
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
  it('广告活动是独立一级路由', async () => {
    isLoggedIn.mockReturnValue(true)
    await router.push('/campaigns')
    expect(router.currentRoute.value.name).toBe('campaigns')
  })
})
