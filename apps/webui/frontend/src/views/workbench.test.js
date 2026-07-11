import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
vi.mock('../api.js', () => ({ api: {
  variantGroup: vi.fn().mockResolvedValue({ ok: true, group: 'G-1', variants: [{ id: 7, spec: 'A' }, { id: 8, spec: 'B' }] }),
  listWarehouses: vi.fn().mockResolvedValue({ warehouses: [] }),
  getLatestTextJob: vi.fn().mockResolvedValue(null),
} }))
import Workbench from './Workbench.vue'
import { useAppStore } from '../stores/app.js'
import { useWorkbenchStore } from '../stores/workbench.js'

describe('Workbench 外壳', () => {
  it('渲染左栏 + 右侧主区容器', () => {
    setActivePinia(createPinia())
    useAppStore().loadDrafts = vi.fn()
    const w = mount(Workbench, { global: { stubs: { DraftListPane: true, VariantGroupBar: true, 'el-button': true } } })
    expect(w.find('.wb-grid').exists()).toBe(true)
    expect(w.find('.wb-left').exists()).toBe(true)
    expect(w.find('.wb-main').exists()).toBe(true)
  })
  it('移除重复顶部发布按钮并把整组发布与单变体发布分开', async () => {
    setActivePinia(createPinia())
    const store = useAppStore()
    store.loadDrafts = vi.fn()
    store.drafts = [{ id: 7, source_title: '商品' }]
    store.selectedId = 7
    const wb = useWorkbenchStore()
    wb.groupKey = 'G-1'
    wb.variants = [{ id: 7, spec: 'A' }, { id: 8, spec: 'B' }]
    wb.currentVariantId = 7
    const w = mount(Workbench, { global: { stubs: {
      DraftListPane: true,
      VariantGroupBar: { template: '<button class="group-stub" @click="$emit(\'publish-group\')">group</button>', emits: ['publish-group'] },
      PipelinePanel: { template: '<button class="single-stub" @click="$emit(\'publish-one\')">single</button>', emits: ['publish-one'] },
      DetailTabs: true,
      'el-button': true,
    } } })

    expect(w.find('.wb-publish-bar').exists()).toBe(false)
    expect(w.find('.group-stub').exists()).toBe(true)
    expect(w.find('.single-stub').exists()).toBe(true)
  })
})
