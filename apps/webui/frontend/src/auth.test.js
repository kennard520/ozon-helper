import { describe, it, expect, beforeEach } from 'vitest'
import { getToken, setAuth, getUser, clearAuth, isLoggedIn, authHeader } from './auth.js'

describe('authHeader (纯函数)', () => {
  it('有 token → Bearer 头', () => {
    expect(authHeader('abc')).toEqual({ Authorization: 'Bearer abc' })
  })
  it('无 token → 空对象', () => {
    expect(authHeader('')).toEqual({})
    expect(authHeader(null)).toEqual({})
  })
})

function makeLS() {
  let m = {}
  return {
    getItem: (k) => (k in m ? m[k] : null),
    setItem: (k, v) => { m[k] = String(v) },
    removeItem: (k) => { delete m[k] },
    clear: () => { m = {} },
  }
}

describe('token 存取 (localStorage)', () => {
  // jsdom(Node26) 不一定提供 window.localStorage，注入内存版保证可测
  beforeEach(() => {
    Object.defineProperty(window, 'localStorage', { value: makeLS(), configurable: true, writable: true })
  })

  it('setAuth/getToken/getUser 往返', () => {
    setAuth('tok123', { id: 7, username: 'alice' })
    expect(getToken()).toBe('tok123')
    expect(getUser()).toEqual({ id: 7, username: 'alice' })
    expect(isLoggedIn()).toBe(true)
  })

  it('clearAuth 清空', () => {
    setAuth('tok', { id: 1, username: 'x' })
    clearAuth()
    expect(getToken()).toBe('')
    expect(getUser()).toBeNull()
    expect(isLoggedIn()).toBe(false)
  })

  it('未登录默认空', () => {
    expect(getToken()).toBe('')
    expect(isLoggedIn()).toBe(false)
  })
})
