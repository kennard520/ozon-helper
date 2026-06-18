import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import DraftDetail from '../src/components/DraftDetail.vue'
import { api } from '../src/api.js'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.spyOn(api, 'requiredCheck').mockResolvedValue({ required: [], optional: [], missing: [], errors: [] })
})
afterEach(() => vi.restoreAllMocks())

const draftWithProposal = {
  id: 1, category_id: '10', type_id: '20', ozon_title: 'ORIG', description: '', images: [], attributes: [],
  ai_proposal: {
    ts: 't', keywords: ['k'],
    fields: { ozon_title: 'RU TITLE', description: 'RU DESC', brand_name: 'Нет бренда' },
    attributes: [
      { id: 9048, name: 'Модель', value: 'X', source: 'ai' },
      { id: 4194, name: 'Тип', value: '', source: 'missing', required: true },
    ],
  },
}

describe('DraftDetail AI 待确认草案', () => {
  it('有草案时渲染待确认区，正式 form 不被覆盖', async () => {
    const w = mount(DraftDetail, { props: { draft: draftWithProposal }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(w.vm.proposalActive).toBe(true)
    expect(w.vm.form.ozon_title).toBe('ORIG')
  })

  it('编辑字段调 aiProposalPatch edit_field', async () => {
    const spy = vi.spyOn(api, 'aiProposalPatch').mockResolvedValue({ ok: true, proposal: draftWithProposal.ai_proposal })
    const w = mount(DraftDetail, { props: { draft: draftWithProposal }, global: { plugins: [ElementPlus] } })
    await w.vm.editProposalField('ozon_title', 'NEW')
    expect(spy).toHaveBeenCalledWith(1, { op: 'edit_field', key: 'ozon_title', value: 'NEW' })
  })

  it('删除特征调 delete_attr', async () => {
    const spy = vi.spyOn(api, 'aiProposalPatch').mockResolvedValue({ ok: true, proposal: draftWithProposal.ai_proposal })
    const w = mount(DraftDetail, { props: { draft: draftWithProposal }, global: { plugins: [ElementPlus] } })
    await w.vm.deleteProposalAttr(9048)
    expect(spy).toHaveBeenCalledWith(1, { op: 'delete_attr', id: 9048 })
  })

  it('应用调 aiProposalApply 并刷新', async () => {
    const spy = vi.spyOn(api, 'aiProposalApply').mockResolvedValue({ ok: true, draft: { id: 1, ozon_title: 'RU TITLE', ai_proposal: null }, unmapped: [] })
    const w = mount(DraftDetail, { props: { draft: draftWithProposal }, global: { plugins: [ElementPlus] } })
    await w.vm.applyProposal()
    expect(spy).toHaveBeenCalledWith(1)
  })

  it('放弃调 discard', async () => {
    const spy = vi.spyOn(api, 'aiProposalPatch').mockResolvedValue({ ok: true, proposal: null })
    const w = mount(DraftDetail, { props: { draft: draftWithProposal }, global: { plugins: [ElementPlus] } })
    await w.vm.discardProposal()
    expect(spy).toHaveBeenCalledWith(1, { op: 'discard' })
  })
})
