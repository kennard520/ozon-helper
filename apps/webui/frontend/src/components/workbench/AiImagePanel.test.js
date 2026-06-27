import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
vi.mock('../../api.js', () => ({ api: {
  imagePlan: vi.fn().mockResolvedValue({ ok: true, plan: [
    { slot_id: 's0', label: '白底主图', action: 'white', status: 'todo' },
    { slot_id: 's1', label: '场景图', action: 'scene', status: 'applied', candidate_url: 'http://g/s1.jpg' },
  ] }),
  designImagePlan: vi.fn().mockResolvedValue({ ok: true, plan: [], count: 0 }),
  generatePlanSlot: vi.fn().mockResolvedValue({ ok: true, draft: { id: 7 } }),
} }))
import { api } from '../../api.js'
import AiImagePanel from './AiImagePanel.vue'

beforeEach(() => { vi.clearAllMocks() })
function factory() {
  return mount(AiImagePanel, { props: { draft: { id: 7 } } })
}

describe('AiImagePanel', () => {
  it('挂载自动 loadPlan 渲槽位', async () => {
    const w = factory()
    await nextTick(); await Promise.resolve(); await Promise.resolve(); await nextTick()
    expect(api.imagePlan).toHaveBeenCalled()
    expect(w.text()).toContain('白底主图'); expect(w.text()).toContain('场景图')
  })
  it('「AI 设计图集」触发 designImagePlan', async () => {
    const w = factory()
    await nextTick(); await Promise.resolve()
    const btn = w.findAll('button').find((b) => b.text().includes('设计'))
    await btn.trigger('click')
    expect(api.designImagePlan).toHaveBeenCalledWith(7, expect.any(Number))
  })
  it('槽位「生成」触发 generatePlanSlot', async () => {
    const w = factory()
    await nextTick(); await Promise.resolve(); await Promise.resolve(); await nextTick()
    const btn = w.findAll('button').find((b) => b.text().includes('生成'))
    await btn.trigger('click')
    expect(api.generatePlanSlot).toHaveBeenCalledWith(7, 's0')
  })
})
