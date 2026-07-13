import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

vi.mock('../../api.js', () => ({
  api: {
    importOzonBySku: vi.fn(),
    syncOzonProducts: vi.fn(),
  },
}))

import { api } from '../../api.js'
import OzonImportDialog from './OzonImportDialog.vue'

const elementStubs = {
  ElDialog: {
    props: ['modelValue', 'title'],
    template: `
      <section v-if="modelValue" class="dialog-stub">
        <h2>{{ title }}</h2>
        <slot />
        <footer><slot name="footer" /></footer>
      </section>
    `,
  },
  ElInput: {
    props: ['modelValue', 'disabled'],
    emits: ['update:modelValue'],
    template: '<input :value="modelValue" :disabled="disabled" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  ElButton: {
    props: ['disabled', 'loading', 'type'],
    emits: ['click'],
    template: '<button :disabled="disabled || loading" @click="$emit(\'click\')"><slot /></button>',
  },
  ElCheckbox: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<label><input type="checkbox" :checked="modelValue" @change="$emit(\'update:modelValue\', $event.target.checked)" /><slot /></label>',
  },
}

function mountDialog(storeClientId = 'C-1') {
  return mount(OzonImportDialog, {
    props: { modelValue: true, storeClientId },
    global: { stubs: elementStubs },
  })
}

async function enterSkuAndSubmit(wrapper, sku) {
  await wrapper.find('.sku-input').setValue(sku)
  await wrapper.find('.sku-submit').trigger('click')
  await flushPromises()
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('OzonImportDialog', () => {
  it.each(['abc', '12.5', '0', '-1', ''])('rejects invalid SKU %j without calling the API', async (sku) => {
    const wrapper = mountDialog()

    await enterSkuAndSubmit(wrapper, sku)

    expect(wrapper.text()).toContain('SKU 必须是正整数')
    expect(api.importOzonBySku).not.toHaveBeenCalled()
  })

  it('disables store-scoped actions when no current store is selected', async () => {
    const wrapper = mountDialog('')
    await wrapper.find('.sku-input').setValue('4998185789')

    expect(wrapper.find('.sku-submit').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.sync-store').attributes('disabled')).toBeDefined()
  })

  it('imports from the current store and emits a created draft with warnings', async () => {
    api.importOzonBySku.mockResolvedValueOnce({
      created: true,
      draft: { id: 42, ozon_title: 'Remote title' },
      conflicts: [],
      warnings: ['部分属性未拉取'],
    })
    const wrapper = mountDialog()

    await enterSkuAndSubmit(wrapper, '4998185789')

    expect(api.importOzonBySku).toHaveBeenCalledWith('4998185789', 'C-1', undefined)
    expect(wrapper.text()).toContain('部分属性未拉取')
    expect(wrapper.emitted('imported')[0][0]).toEqual({
      draft: { id: 42, ozon_title: 'Remote title' },
      created: true,
      warnings: ['部分属性未拉取'],
    })
  })

  it('shows local and remote conflict values with every field unchecked by default', async () => {
    api.importOzonBySku.mockResolvedValueOnce({
      created: false,
      draft: { id: 7, ozon_title: '本地标题' },
      conflicts: [
        { field: 'ozon_title', local: '本地标题', remote: '远端标题' },
        { field: 'description', local: '本地描述', remote: '远端描述' },
      ],
      warnings: ['属性信息不完整'],
    })
    const wrapper = mountDialog()

    await enterSkuAndSubmit(wrapper, '4998185789')

    expect(wrapper.text()).toContain('本地标题')
    expect(wrapper.text()).toContain('远端标题')
    expect(wrapper.text()).toContain('本地描述')
    expect(wrapper.text()).toContain('远端描述')
    expect(wrapper.text()).toContain('属性信息不完整')
    expect(wrapper.findAll('.conflict-checkbox input').every((input) => !input.element.checked)).toBe(true)
    expect(wrapper.emitted('imported')).toBeUndefined()
  })

  it('applies only checked conflict fields through selected_fields', async () => {
    api.importOzonBySku
      .mockResolvedValueOnce({
        created: false,
        draft: { id: 7 },
        conflicts: [
          { field: 'ozon_title', local: '本地标题', remote: '远端标题' },
          { field: 'description', local: '本地描述', remote: '远端描述' },
        ],
        warnings: [],
      })
      .mockResolvedValueOnce({
        created: false,
        draft: { id: 7, ozon_title: '远端标题' },
        conflicts: [],
        warnings: ['已保留未选择字段'],
      })
    const wrapper = mountDialog()
    await enterSkuAndSubmit(wrapper, '4998185789')

    await wrapper.findAll('.conflict-checkbox input')[0].setValue(true)
    await wrapper.find('.apply-conflicts').trigger('click')
    await flushPromises()

    expect(api.importOzonBySku).toHaveBeenLastCalledWith('4998185789', 'C-1', ['ozon_title'])
    expect(wrapper.emitted('imported')[0][0]).toEqual({
      draft: { id: 7, ozon_title: '远端标题' },
      created: false,
      warnings: ['已保留未选择字段'],
    })
  })

  it('renders loading and error states', async () => {
    let rejectImport
    api.importOzonBySku.mockReturnValueOnce(new Promise((resolve, reject) => { rejectImport = reject }))
    const wrapper = mountDialog()

    await wrapper.find('.sku-input').setValue('4998185789')
    await wrapper.find('.sku-submit').trigger('click')
    expect(wrapper.text()).toContain('正在导入')
    expect(wrapper.find('.is-loading').attributes('role')).toBe('status')
    expect(wrapper.find('.is-loading').attributes('aria-live')).toBe('polite')

    rejectImport(new Error('Ozon 暂时不可用'))
    await flushPromises()
    expect(wrapper.text()).toContain('Ozon 暂时不可用')
    expect(wrapper.find('.is-error').attributes('role')).toBe('alert')
    expect(wrapper.find('.is-error').attributes('aria-live')).toBe('assertive')
  })

  it('gives the SKU input an explicit accessible name', () => {
    const wrapper = mountDialog()

    expect(wrapper.find('label[for="ozon-sku-input"]').text()).toBe('Ozon SKU')
    expect(wrapper.find('#ozon-sku-input').attributes('aria-label')).toBe('Ozon SKU')
  })

  it('can synchronize all products for the current store', async () => {
    api.syncOzonProducts.mockResolvedValueOnce({ pulled: 12, created: 3, updated: 9, failed: 0 })
    const wrapper = mountDialog()

    await wrapper.find('.sync-store').trigger('click')
    await flushPromises()

    expect(api.syncOzonProducts).toHaveBeenCalledWith('C-1')
    expect(wrapper.text()).toContain('同步完成')
    expect(wrapper.text()).toContain('12')
  })

  it('treats a resolved fatal sync response with no progress as an error', async () => {
    api.syncOzonProducts.mockResolvedValueOnce({
      created: 0,
      updated: 0,
      preserved: 0,
      failed: 1,
      pulled: 0,
      drafts: [],
      errors: ['商品列表请求失败'],
      warnings: [],
    })
    const wrapper = mountDialog()

    await wrapper.find('.sync-store').trigger('click')
    await flushPromises()

    expect(wrapper.find('.is-error').attributes('role')).toBe('alert')
    expect(wrapper.text()).toContain('同步失败')
    expect(wrapper.text()).toContain('失败 1 个')
    expect(wrapper.text()).toContain('商品列表请求失败')
    expect(wrapper.text()).not.toContain('同步完成')
  })

  it('discloses failed count and errors for a partially successful sync', async () => {
    api.syncOzonProducts.mockResolvedValueOnce({
      phase: 'done',
      visibility: 'ALL',
      store_client_id: 'C-1',
      created: 1,
      updated: 0,
      preserved: 0,
      failed: 1,
      pulled: 1,
      drafts: [{ id: 42 }],
      errors: ['offer_id BAD: bad product payload'],
      warnings: ['属性拉取失败，尺寸和商品属性留空'],
    })
    const wrapper = mountDialog()

    await wrapper.find('.sync-store').trigger('click')
    await flushPromises()

    expect(wrapper.find('.is-done').attributes('role')).toBe('status')
    expect(wrapper.text()).toContain('同步部分完成')
    expect(wrapper.text()).toContain('失败 1 个')
    expect(wrapper.text()).toContain('offer_id BAD: bad product payload')
    expect(wrapper.text()).toContain('属性拉取失败，尺寸和商品属性留空')
    expect(wrapper.text()).not.toContain('同步完成：')
  })
})
