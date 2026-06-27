import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
vi.mock('../api.js', () => ({ api: {
  aiProposalPatch: vi.fn().mockResolvedValue({ ok: true, proposal: { fields: { ozon_title: '改后' }, attributes: [] } }),
  aiProposalApply: vi.fn().mockResolvedValue({ ok: true, draft: { id: 7, ai_proposal: null }, unmapped: [] }),
  aiGenerate: vi.fn().mockResolvedValue({ ok: true, mode: 'draft' }),
  aiCopy: vi.fn().mockResolvedValue({ ok: true, mode: 'draft' }),
} }))
import { api } from '../api.js'
import { useProposal } from './useProposal.js'

beforeEach(() => { vi.clearAllMocks() })
function mkDraft(prop) { return ref({ id: 7, ai_proposal: prop }) }
const PROP = {
  fields: { ozon_title: 'T', description: 'D' },
  attributes: [
    { id: 100, name: '材料', value: '棉', source: 'ai' },
    { id: 23171, name: '标签', value: '#a #b', source: 'ai' },
    { id: 200, name: '颜色', value: '', source: 'missing', required: true },
  ],
}

describe('useProposal', () => {
  it('hasProposal + 派生 aiAttrs/missingAttrs/tags', () => {
    const p = useProposal(mkDraft(PROP), { onApplied: vi.fn() })
    expect(p.hasProposal.value).toBe(true)
    expect(p.aiAttrs.value.map(a => a.id)).toEqual([100])   // 排除 23171
    expect(p.missingAttrs.value.map(a => a.id)).toEqual([200])
    expect(p.tags.value).toBe('#a #b')
  })

  it('无草案 hasProposal=false', () => {
    const p = useProposal(mkDraft(null), { onApplied: vi.fn() })
    expect(p.hasProposal.value).toBe(false)
  })

  it('editField 调 patch(edit_field) 并用返回更新', async () => {
    const p = useProposal(mkDraft(PROP), { onApplied: vi.fn() })
    await p.editField('ozon_title', '改后')
    expect(api.aiProposalPatch).toHaveBeenCalledWith(7, { op: 'edit_field', key: 'ozon_title', value: '改后' })
    expect(p.proposal.value.fields.ozon_title).toBe('改后')
  })

  it('editAttr / deleteAttr / editTags', async () => {
    const p = useProposal(mkDraft(PROP), { onApplied: vi.fn() })
    await p.editAttr(100, '涤纶')
    expect(api.aiProposalPatch).toHaveBeenCalledWith(7, { op: 'edit_attr', id: 100, value: '涤纶' })
    await p.deleteAttr(100)
    expect(api.aiProposalPatch).toHaveBeenCalledWith(7, { op: 'delete_attr', id: 100 })
    await p.editTags('#x')
    expect(api.aiProposalPatch).toHaveBeenCalledWith(7, { op: 'edit_attr', id: 23171, value: '#x' })
  })

  it('apply 调 aiProposalApply + onApplied', async () => {
    const onApplied = vi.fn()
    const p = useProposal(mkDraft(PROP), { onApplied })
    const r = await p.apply()
    expect(api.aiProposalApply).toHaveBeenCalledWith(7)
    expect(onApplied).toHaveBeenCalled()
    expect(r.unmapped).toEqual([])
  })

  it('discard 调 patch(discard) + onApplied', async () => {
    const onApplied = vi.fn()
    const p = useProposal(mkDraft(PROP), { onApplied })
    await p.discard()
    expect(api.aiProposalPatch).toHaveBeenCalledWith(7, { op: 'discard' })
    expect(onApplied).toHaveBeenCalled()
  })

  it('generate(full/copy) 调对应 api + onApplied', async () => {
    const onApplied = vi.fn()
    const p = useProposal(mkDraft(null), { onApplied })
    await p.generate('full')
    expect(api.aiGenerate).toHaveBeenCalledWith(7)
    await p.generate('copy')
    expect(api.aiCopy).toHaveBeenCalledWith(7)
    expect(onApplied).toHaveBeenCalledTimes(2)
  })
})
