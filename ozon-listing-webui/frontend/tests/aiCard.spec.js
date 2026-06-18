import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import DraftDetail from '../src/components/DraftDetail.vue'
import { api } from '../src/api.js'

const draft = {
  id: 7, source_platform: '1688', source_title: '车载支架', ozon_title: '',
  category_id: '', type_id: '', price: '', stock: 0,
  images: ['https://cbu01.alicdn.com/a.jpg'],
  local_images: ['/media/draft-1/00.jpg'],
  video_url: '',
  weight_g: 0, length_mm: 0, width_mm: 0, height_mm: 0,
  supplier: '', offer_id: '', attributes: [], validation_errors: [],
}

const AI_MOCK_PROPOSAL = {
  ozon_title: 'Держатель',
  category_id: '1',
  type_id: '2',
  description: 'Длинное описание товара',
  attributes: [
    { id: 4180, values: [{ value: 'металл' }] },
    { id: 4191, values: [{ value: 'Отличный товар для дома' }] },
  ],
  brand_name: 'Нет бренда',
  weight_g: 600,
  length_mm: 20,
  width_mm: 15,
  height_mm: 10,
}

const AI_MOCK_REPORT = {
  category_path: 'Авто/Держатель',
  category_fallback: false,
  brand_warning: '',
  mapped: [
    { id: 4180, name: 'Материал', value: 'металл' },
    { id: 4191, name: 'Аннотация', value: 'Отличный товар для дома' },
  ],
  unmapped: [{ id: 5000, name: 'Цвет', value: 'синий' }],
  keywords: ['держатель', 'авто'],
}

const APPLIED_DRAFT = {
  ...draft,
  ozon_title: 'Держатель',
  category_id: '1',
  type_id: '2',
  description: 'Длинное описание товара',
  attributes: AI_MOCK_PROPOSAL.attributes,
}

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => vi.restoreAllMocks())

describe('DraftDetail AI 生成卡片（内联展示）', () => {
  it('doAiGenerate 调用 api.aiGenerate，applied 模式下回填表单', async () => {
    const aiSpy = vi.spyOn(api, 'aiGenerate').mockResolvedValue({
      ok: true,
      mode: 'applied',
      draft: APPLIED_DRAFT,
      proposal: AI_MOCK_PROPOSAL,
      report: AI_MOCK_REPORT,
    })
    vi.spyOn(api, 'patchDraft').mockResolvedValue({ draft: APPLIED_DRAFT })
    const reqSpy = vi.spyOn(api, 'requiredCheck').mockResolvedValue({ required: [], optional: [], missing: [] })

    const w = mount(DraftDetail, { global: { plugins: [ElementPlus] }, props: { draft } })
    await w.vm.doAiGenerate()
    await flushPromises()

    // 1. aiGenerate 应被调用
    expect(aiSpy).toHaveBeenCalledWith(7)

    // 2. 无弹窗状态（aiPreviewVisible 不存在或不为 true）
    expect(w.vm.aiPreviewVisible).toBeFalsy()

    // 3. applied 模式：form 已回填（description 来自 applied draft）
    expect(w.vm.form.description).toBe('Длинное описание товара')

    // 4. requiredCheck 已被调用（刷新必填属性区）
    expect(reqSpy).toHaveBeenCalled()
  })

  it('draft 模式：不回填 form，调 listDrafts 刷新草案', async () => {
    const freshDraftWithProposal = {
      ...draft,
      ai_proposal: {
        ts: 't', keywords: ['держатель'],
        fields: { ozon_title: 'Держатель' },
        attributes: [],
      },
    }
    vi.spyOn(api, 'aiGenerate').mockResolvedValue({
      ok: true,
      mode: 'draft',
    })
    vi.spyOn(api, 'patchDraft').mockResolvedValue({ draft })
    vi.spyOn(api, 'requiredCheck').mockResolvedValue({ required: [], optional: [], missing: [] })
    const listSpy = vi.spyOn(api, 'listDrafts').mockResolvedValue({ drafts: [freshDraftWithProposal] })

    const w = mount(DraftDetail, { global: { plugins: [ElementPlus] }, props: { draft } })
    await w.vm.doAiGenerate()
    await flushPromises()

    // draft 模式下调 listDrafts 刷新草稿
    expect(listSpy).toHaveBeenCalled()
    // form 未被回填（还是初始值）
    expect(w.vm.form.ozon_title).toBe('')
  })
})
