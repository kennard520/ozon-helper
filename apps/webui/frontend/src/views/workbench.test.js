import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import Workbench from './Workbench.vue'
import { useAppStore } from '../stores/app.js'
import { useWorkbenchStore } from '../stores/workbench.js'

const ElButtonStub = {
  emits: ['click'],
  template: '<button @click="$emit(\'click\')"><slot /></button>',
}

const OzonImportDialogStub = {
  props: ['modelValue', 'storeClientId'],
  emits: ['update:modelValue', 'imported'],
  template: `
    <div class="ozon-import-dialog-stub" :data-open="String(modelValue)" :data-store-id="storeClientId">
      <button v-if="modelValue" class="finish-import" @click="$emit('imported', { draft: { id: 42 } })">
        finish import
      </button>
    </div>
  `,
}

describe('Workbench 外壳', () => {
  it('渲染左栏 + 右侧主区容器', () => {
    setActivePinia(createPinia())
    useAppStore().loadDrafts = vi.fn()
    const w = mount(Workbench, { global: { stubs: { DraftListPane: true, VariantGroupBar: true, OzonImportDialog: true, 'el-button': true } } })
    expect(w.find('.wb-grid').exists()).toBe(true)
    expect(w.find('.wb-left').exists()).toBe(true)
    expect(w.find('.wb-main').exists()).toBe(true)
  })

  it('从 Ozon 导入后刷新草稿并选中新草稿', async () => {
    setActivePinia(createPinia())
    const store = useAppStore()
    store.currentStore = 'store-7'
    store.loadDrafts = vi.fn().mockResolvedValue()
    useWorkbenchStore().loadForDraft = vi.fn()

    const w = mount(Workbench, {
      global: {
        stubs: {
          DraftListPane: true,
          VariantGroupBar: true,
          OzonImportDialog: OzonImportDialogStub,
          'el-button': ElButtonStub,
        },
      },
    })
    await flushPromises()
    store.loadDrafts.mockClear()

    const importButton = w.findAll('button').find((button) => button.text() === '从 Ozon 导入')
    expect(importButton).toBeTruthy()
    await importButton.trigger('click')

    const dialog = w.find('.ozon-import-dialog-stub')
    expect(dialog.attributes('data-open')).toBe('true')
    expect(dialog.attributes('data-store-id')).toBe('store-7')

    await w.find('.finish-import').trigger('click')
    await flushPromises()

    expect(store.loadDrafts).toHaveBeenCalledTimes(1)
    expect(store.selectedId).toBe(42)
  })
})
