import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import DraftDetail from '../src/components/DraftDetail.vue'
import { api } from '../src/api.js'

// ── api.js unit tests ────────────────────────────────────────────────────────

describe('api.publishGroup', () => {
  beforeEach(() => {
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ published: true, count: 2, model_name: 'Тест' }) })
    )
  })

  it('POST /api/ext/publish-group with { variant_group } when no store_client_id', async () => {
    await api.publishGroup('G1')
    const [url, opts] = global.fetch.mock.calls[0]
    expect(url).toBe('/api/ext/publish-group')
    expect(opts.method).toBe('POST')
    expect(JSON.parse(opts.body)).toEqual({ variant_group: 'G1' })
  })

  it('includes store_client_id when provided', async () => {
    await api.publishGroup('G2', '777')
    const [, opts] = global.fetch.mock.calls[0]
    expect(JSON.parse(opts.body)).toEqual({ variant_group: 'G2', store_client_id: '777' })
  })

  it('omits store_client_id when falsy', async () => {
    await api.publishGroup('G3', '')
    const [, opts] = global.fetch.mock.calls[0]
    expect(JSON.parse(opts.body)).toEqual({ variant_group: 'G3' })
  })
})

// ── DraftDetail button visibility tests ─────────────────────────────────────

const baseDraft = {
  id: 1, source_platform: 'ozon', source_title: 'Тест', ozon_title: '',
  category_id: '', type_id: '', price: '', stock: 0, images: [],
  weight_g: 0, length_mm: 0, width_mm: 0, height_mm: 0,
  supplier: '', offer_id: '', attributes: [], validation_errors: [],
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.spyOn(api, 'requiredCheck').mockResolvedValue({ required: [], missing: [], errors: [] })
})

describe('DraftDetail 整组发布按钮', () => {
  it('隐藏：draft 无 source_raw.variant_group 时不渲染整组发布按钮', () => {
    const w = mount(DraftDetail, {
      global: { plugins: [ElementPlus] },
      props: { draft: { ...baseDraft, source_raw: null } },
    })
    expect(w.text()).not.toContain('发布整组')
  })

  it('隐藏：source_raw.variant_group 为空字符串时不渲染整组发布按钮', () => {
    const w = mount(DraftDetail, {
      global: { plugins: [ElementPlus] },
      props: { draft: { ...baseDraft, source_raw: { variant_group: '' } } },
    })
    expect(w.text()).not.toContain('发布整组')
  })

  it('显示：source_raw.variant_group 有值时渲染整组发布按钮', () => {
    const w = mount(DraftDetail, {
      global: { plugins: [ElementPlus] },
      props: { draft: { ...baseDraft, source_raw: { variant_group: '12345678' } } },
    })
    expect(w.text()).toContain('发布整组')
  })

  it('variantGroup computed 返回正确字符串', () => {
    const w = mount(DraftDetail, {
      global: { plugins: [ElementPlus] },
      props: { draft: { ...baseDraft, source_raw: { variant_group: 'SKU999' } } },
    })
    expect(w.vm.variantGroup).toBe('SKU999')
  })

  it('variantGroup computed 在无 source_raw 时返回空串', () => {
    const w = mount(DraftDetail, {
      global: { plugins: [ElementPlus] },
      props: { draft: { ...baseDraft } },
    })
    expect(w.vm.variantGroup).toBe('')
  })

  it('点整组发布确认后调用 api.publishGroup 并展示成功消息', async () => {
    const spy = vi.spyOn(api, 'publishGroup').mockResolvedValue({ published: true, count: 3, model_name: 'Ящик' })

    const w = mount(DraftDetail, {
      global: { plugins: [ElementPlus] },
      props: { draft: { ...baseDraft, source_raw: { variant_group: 'G42' } } },
    })

    // 直接调用 onPublishGroup，跳过 ElMessageBox（已 confirm）
    // 注入自动确认：替换 ElMessageBox.confirm
    const { ElMessageBox } = await import('element-plus')
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')

    await w.vm.onPublishGroup()
    await flushPromises()

    expect(spy).toHaveBeenCalledWith('G42')
  })

  it('点整组发布取消后不调用 api.publishGroup', async () => {
    const spy = vi.spyOn(api, 'publishGroup').mockResolvedValue({ published: true, count: 1, model_name: 'X' })

    const w = mount(DraftDetail, {
      global: { plugins: [ElementPlus] },
      props: { draft: { ...baseDraft, source_raw: { variant_group: 'G99' } } },
    })

    const { ElMessageBox } = await import('element-plus')
    vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue(new Error('cancel'))

    await w.vm.onPublishGroup()
    await flushPromises()

    expect(spy).not.toHaveBeenCalled()
  })
})
