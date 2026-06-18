// 多用户鉴权：JWT 存 localStorage；req() 注入 Authorization 头；401 触发登出。
const TOKEN_KEY = 'ozon_token'
const USER_KEY = 'ozon_user'

// 显式取 window.localStorage（浏览器/jsdom 都有）；别用裸 localStorage——
// Node 26 自带实验性 localStorage 全局会盖过 jsdom 的、且默认不可用。
function _ls() {
  try {
    return (typeof window !== 'undefined' && window.localStorage) ? window.localStorage : null
  } catch (e) {
    return null
  }
}

export function getToken() {
  const ls = _ls()
  try { return (ls && ls.getItem(TOKEN_KEY)) || '' } catch (e) { return '' }
}

export function setAuth(token, user) {
  const ls = _ls()
  if (!ls) return
  try {
    ls.setItem(TOKEN_KEY, token || '')
    if (user) ls.setItem(USER_KEY, JSON.stringify(user))
  } catch (e) { /* ignore */ }
}

export function getUser() {
  const ls = _ls()
  try { return JSON.parse((ls && ls.getItem(USER_KEY)) || 'null') } catch (e) { return null }
}

export function clearAuth() {
  const ls = _ls()
  if (!ls) return
  try {
    ls.removeItem(TOKEN_KEY)
    ls.removeItem(USER_KEY)
  } catch (e) { /* ignore */ }
}

export function isLoggedIn() {
  return !!getToken()
}

// 给定 token 返回鉴权头（纯函数，便于单测）
export function authHeader(token) {
  return token ? { Authorization: 'Bearer ' + token } : {}
}
