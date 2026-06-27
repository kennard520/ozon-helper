import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
vi.mock('../../api.js', () => ({ api: {
  aiProposalPatch: vi.fn().mockResolvedValue({ ok: true, proposal: null }),
  aiProposalApply: vi.fn().mockResolvedValue({ ok: true, draft: { id: 7 }, unmapped: [] }),
  aiGenerate: vi.fn().mockResolvedValue({ ok: true, mode: 'draft' }),
  aiCopy: vi.fn().mockResolvedValue({ ok: true, mode: 'draft' }),
} }))
import { api } from '../../api.js'
import ProposalPanel from './ProposalPanel.vue'

beforeEach(() => { vi.clearAllMocks() })
const PROP = {
  fields: { ozon_title: 'T俄', description: 'D俄' },
  attributes: [
    { id: 100, name: '材料', value: '棉', source: 'ai' },
    { id: 200, name: '颜色', value: '', source: 'missing', required: true },
  ],
}
function factory(ai_proposal) {
  return mount(ProposalPanel, {
    props: { draft: { id: 7, ai_proposal } },
    global: {
      stubs: {
        ElInput: { template: '<input />' },
        ElMessage: true,
      },
    },
  })
}

describe('ProposalPanel', () => {
  it('无草案：渲生成按钮，点触发 aiGenerate', async () => {
    const w = factory(null)
    const btn = w.findAll('button').find((b) => b.text().includes('生成草案'))
    expect(btn).toBeTruthy()
    await btn.trigger('click')
    expect(api.aiGenerate).toHaveBeenCalledWith(7)
  })
  it('有草案：渲标题/AI属性/缺失项', () => {
    const w = factory(PROP)
    expect(w.text()).toContain('待确认')
    expect(w.text()).toContain('材料')
    expect(w.text()).toContain('颜色')
  })
  it('应用按钮触发 aiProposalApply', async () => {
    const w = factory(PROP)
    const btn = w.findAll('button').find((b) => b.text().includes('应用'))
    await btn.trigger('click')
    expect(api.aiProposalApply).toHaveBeenCalledWith(7)
  })
  it('放弃按钮触发 discard patch', async () => {
    const w = factory(PROP)
    const btn = w.findAll('button').find((b) => b.text().includes('放弃'))
    await btn.trigger('click')
    expect(api.aiProposalPatch).toHaveBeenCalledWith(7, { op: 'discard' })
  })
})
