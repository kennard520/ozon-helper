import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import Workbench from './Workbench.vue'
import { useAppStore } from '../stores/app.js'
import { useWorkbenchStore } from '../stores/workbench.js'

function deferred() {
  let resolve
  const promise = new Promise((done) => { resolve = done })
  return { promise, resolve }
}

const ElButtonStub = {
  emits: ['click'],
  template: '<button @click="$emit(\'click\')"><slot /></button>',
}

const OzonImportDialogStub = {
  props: ['modelValue', 'storeClientId'],
  emits: ['update:modelValue', 'imported'],
  template: `
    <div class="ozon-import-dialog-stub" :data-open="String(modelValue)" :data-store-id="storeClientId">
      <button v-if="modelValue" class="finish-import" @click="$emit('imported', { draft: { id: 42, store_client_id: 'store-7', source_title: 'Imported Ozon product' } })">
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
    store.filter = 'published'
    store.page = 3
    store.selectedId = 7
    store.drafts = [{ id: 7, store_client_id: 'store-7', source_title: 'Existing draft' }]
    const refresh = deferred()
    store.loadDrafts = vi.fn()
      .mockResolvedValueOnce(true)
      .mockImplementationOnce(async () => {
        await refresh.promise
        store.drafts = [{ id: 9, store_client_id: 'store-7', source_title: 'First page draft' }]
        return true
      })
    const wb = useWorkbenchStore()
    wb.loadForDraft = vi.fn()

    const w = mount(Workbench, {
      global: {
        stubs: {
          DraftListPane: true,
          VariantGroupBar: true,
          PipelinePanel: true,
          DetailTabs: true,
          OzonImportDialog: OzonImportDialogStub,
          'el-button': ElButtonStub,
        },
      },
    })
    await flushPromises()
    wb.loadForDraft.mockClear()

    const importButton = w.findAll('button').find((button) => button.text() === '从 Ozon 导入')
    expect(importButton).toBeTruthy()
    await importButton.trigger('click')

    const dialog = w.find('.ozon-import-dialog-stub')
    expect(dialog.attributes('data-open')).toBe('true')
    expect(dialog.attributes('data-store-id')).toBe('store-7')

    await w.find('.finish-import').trigger('click')
    expect(store.filter).toBe('all')
    expect(store.page).toBe(1)
    expect(store.selectedId).toBe(7)

    refresh.resolve()
    await flushPromises()

    expect(store.selectedId).toBe(42)
    expect(store.selectedDraft).toMatchObject({ id: 42, store_client_id: 'store-7' })
    expect(w.find('.wb-empty').exists()).toBe(false)
    expect(wb.loadForDraft).toHaveBeenCalledWith(42)
  })

  it('导入刷新期间切店不会采用旧店草稿', async () => {
    setActivePinia(createPinia())
    const store = useAppStore()
    store.currentStore = 'store-7'
    const importRefresh = deferred()
    store.loadDrafts = vi.fn()
      .mockResolvedValueOnce(true)
      .mockImplementationOnce(() => importRefresh.promise)
      .mockImplementationOnce(async () => {
        store.drafts = [{ id: 99, store_client_id: 'store-8', source_title: 'New store draft' }]
        return true
      })
    const wb = useWorkbenchStore()
    wb.loadForDraft = vi.fn()

    const w = mount(Workbench, {
      global: {
        stubs: {
          DraftListPane: true,
          VariantGroupBar: true,
          PipelinePanel: true,
          DetailTabs: true,
          OzonImportDialog: OzonImportDialogStub,
          'el-button': ElButtonStub,
        },
      },
    })
    await flushPromises()
    wb.loadForDraft.mockClear()

    await w.findAll('button').find((button) => button.text() === '从 Ozon 导入').trigger('click')
    await w.find('.finish-import').trigger('click')
    store.setCurrentStore('store-8')
    await flushPromises()

    importRefresh.resolve(true)
    await flushPromises()

    expect(store.currentStore).toBe('store-8')
    expect(store.drafts).toEqual([{ id: 99, store_client_id: 'store-8', source_title: 'New store draft' }])
    expect(store.selectedId).toBeNull()
    expect(wb.loadForDraft).not.toHaveBeenCalledWith(42)
  })
})
