import { describe, it, expect } from 'vitest'
import { allowedInLite, publishLabel } from './local-lite.js'

describe('local lite UI policy', () => {
  it('keeps editing and setup routes but blocks operations pages', () => {
    for (const p of ['/', '/stores', '/settings', '/login']) expect(allowedInLite(p)).toBe(true)
    for (const p of ['/wallet', '/analytics', '/users', '/fulfillment']) expect(allowedInLite(p)).toBe(false)
  })
  it('does not treat submission as platform success', () => {
    expect(publishLabel({ task_id: 12, published: false })).toBe('已提交，平台处理中')
    expect(publishLabel({ published: true })).toBe('发布成功')
    expect(publishLabel({ errors: ['media failed'] })).toBe('发布失败')
  })
})
