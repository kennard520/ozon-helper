import { describe, it, expect } from 'vitest'
import OzonHelperBridge from '../common/bridge.js'

const { buildExtRequest, candidateBases, authHeader } = OzonHelperBridge

describe('authHeader (多用户 JWT)', () => {
  it('有 token → Bearer 头', () => {
    expect(authHeader('jwt123')).toEqual({ Authorization: 'Bearer jwt123' })
  })
  it('无 token → 空对象', () => {
    expect(authHeader('')).toEqual({})
    expect(authHeader(null)).toEqual({})
    expect(authHeader(undefined)).toEqual({})
  })
})

describe('buildExtRequest (relative path)', () => {
  it('ping → GET, 无 body', () => {
    expect(buildExtRequest('ping')).toEqual({ path: '/api/ext/ping', method: 'GET', body: null })
  })
  it('snapshots → GET 带 query', () => {
    const r = buildExtRequest('snapshots', { product_id: '9' })
    expect(r.method).toBe('GET')
    expect(r.path).toBe('/api/ext/snapshots?product_id=9')
    expect(r.body).toBeNull()
  })
  it('collect → POST，body 为 JSON', () => {
    const r = buildExtRequest('collect', { url: 'u' })
    expect(r.method).toBe('POST')
    expect(r.path).toBe('/api/ext/collect')
    expect(JSON.parse(r.body)).toEqual({ url: 'u' })
  })
  it('collectParsed → POST', () => {
    expect(buildExtRequest('collectParsed', { url: 'u', data: {} }).path).toBe('/api/ext/collect-parsed')
  })
  it('未知类型 → null', () => {
    expect(buildExtRequest('nope')).toBeNull()
  })
})

describe('candidateBases', () => {
  it('返回候选 base 列表', () => {
    const b = candidateBases()
    expect(b[0]).toBe('http://127.0.0.1:8585')
    expect(b).toContain('http://127.0.0.1:5050')
    expect(b.length).toBe(10)
  })
})
