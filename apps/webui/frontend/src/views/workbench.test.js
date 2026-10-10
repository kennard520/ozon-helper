import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const ops = vi.hoisted(() => ({
  doPublish: vi.fn().mockResolvedValue({ published: true }),
  doPublishGroup: vi.fn().mockResolvedValue({ published: true }),
  doDelete: vi.fn(),
  doBatchUpdate: vi.fn(),
  doBatchPublish: vi.fn(),
  loadWarehouses: vi.fn(),
  publishResult: null,
  warehouses: [],
  groupPublishing: false,
}))

vi.mock('../composables/useDraftBatchOps.js', () => ({
  useDraftBatchOps: () => ops,
}))

vi.mock('../api.js', () => ({ api: {
  variantGroup: vi.fn().mockResolvedValue({ ok: true, group: '', count: 0, variants: [] }),
  getLatestTextJob: vi.fn().mockResolvedValue({ status: 'done' }),
} }))

import Workbench from './Workbench.vue'
import { useAppStore } from '../stores/app.js'
import { useWorkbenchStore } from '../stores/workbench.js'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('Workbench shell', () => {
  it('local mode hides AI and saves before publishing the current draft', async () => {
    const store = useAppStore()
    store.runtime = { local_lite: true }
    store.loadDrafts = vi.fn()
    store.selectedId = 1316
    store.drafts = [{ id: 1316, source_title: 'local draft' }]
    const saved = vi.fn().mockResolvedValue(undefined)
    const w = mount(Workbench, { global: { stubs: {
      DraftListPane: true, VariantGroupBar: true, PipelinePanel: true,
      DetailTabs: { template: '<div/>', methods: { savePending: saved } },
      'el-button': { template: '<button><slot/></button>' },
    } } })
    await flushPromises()
    expect(w.find('pipeline-panel-stub').exists()).toBe(false)
    await w.find('.wb-publish-bar button').trigger('click')
    await flushPromises()
    expect(saved).toHaveBeenCalled()
    expect(ops.doPublish).toHaveBeenCalledWith(store.selectedDraft)
    expect(ops.doPublishGroup).not.toHaveBeenCalled()
  })
  it('renders sidebar and main containers', () => {
    useAppStore().loadDrafts = vi.fn()
    const w = mount(Workbench, { global: { stubs: { DraftListPane: true, VariantGroupBar: true, 'el-button': true } } })
    expect(w.find('.wb-grid').exists()).toBe(true)
    expect(w.find('.wb-left').exists()).toBe(true)
    expect(w.find('.wb-main').exists()).toBe(true)
  })

  it('publishes only the selected variant from the pipeline publish card', async () => {
    const store = useAppStore()
    store.loadDrafts = vi.fn()
    store.selectedId = 1316
    store.drafts = [{ id: 1316, source_title: 'current', source_url: 'https://example.com/p' }]
    const w = mount(Workbench, {
      global: {
        stubs: {
          DraftListPane: true,
          VariantGroupBar: true,
          DetailTabs: true,
          'el-button': true,
          PipelinePanel: {
            emits: ['publish-one'],
            template: '<button class="pipeline-publish" @click="$emit(\'publish-one\')">publish one</button>',
          },
        },
      },
    })

    await flushPromises()
    await w.find('.pipeline-publish').trigger('click')

    expect(ops.doPublish).toHaveBeenCalledWith(store.selectedDraft)
    expect(ops.doPublishGroup).not.toHaveBeenCalled()
  })

  it('publishes the right-side current variant when it differs from the list selection', async () => {
    const store = useAppStore()
    const wb = useWorkbenchStore()
    store.loadDrafts = vi.fn()
    store.selectedId = 2
    store.drafts = [
      { id: 1, source_title: 'first variant', source_url: 'https://example.com/first' },
      { id: 2, source_title: 'second variant', source_url: 'https://example.com/second' },
    ]
    wb.variants = [{ id: 1, spec: 'first' }, { id: 2, spec: 'second' }]
    wb.currentVariantId = 1

    const w = mount(Workbench, {
      global: {
        stubs: {
          DraftListPane: true,
          VariantGroupBar: true,
          DetailTabs: true,
          'el-button': true,
          PipelinePanel: {
            emits: ['publish-one'],
            template: '<button class="pipeline-publish" @click="$emit(\'publish-one\')">publish one</button>',
          },
        },
      },
    })

    await flushPromises()
    wb.variants = [{ id: 1, spec: 'first' }, { id: 2, spec: 'second' }]
    wb.currentVariantId = 1
    await w.find('.pipeline-publish').trigger('click')

    expect(ops.doPublish).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }))
    expect(ops.doPublish).not.toHaveBeenCalledWith(expect.objectContaining({ id: 2 }))
  })
})
