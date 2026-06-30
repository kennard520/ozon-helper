import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

// mock element-plus 的 ElMessageBox.confirm（删除确认弹窗）
vi.mock('element-plus', () => ({
  ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
}))
// mock api.deleteDraft（删除变体调它）
vi.mock('../../api.js', () => ({ api: {
  deleteDraft: vi.fn().mockResolvedValue({ ok: true }),
  getLatestTextJob: vi.fn().mockResolvedValue(null),
} }))

import { ElMessageBox } from 'element-plus'
import { api } from '../../api.js'
import { useWorkbenchStore } from '../../stores/workbench.js'
import VariantGroupBar from './VariantGroupBar.vue'

function setup() {
  setActivePinia(createPinia())
  const wb = useWorkbenchStore()
  wb.variants = [
    { id: 1, spec: '雾灰·350ml', price: 1190, status: 'ready', image: 'a.jpg', done: 3 },
    { id: 2, spec: '雾灰·500ml', price: 1290, status: 'ready', image: 'b.jpg', done: 5 },
    { id: 3, spec: '哑黑·350ml', price: 1190, status: 'invalid', image: '', done: 0 },
  ]
  wb.currentVariantId = 1
  const w = mount(VariantGroupBar)
  return { w, wb }
}

beforeEach(() => { vi.clearAllMocks() })

describe('VariantGroupBar', () => {
  it('渲染 N 个胶囊 + 标题总数', () => {
    const { w } = setup()
    expect(w.findAll('.vpill')).toHaveLength(3)
    expect(w.text()).toContain('共 3 个变体')
    expect(w.text()).toContain('雾灰·350ml')
    expect(w.text()).toContain('3/7')
  })

  it('点胶囊设当前变体', async () => {
    const { w, wb } = setup()
    const pills = w.findAll('.vpill')
    await pills[1].trigger('click')
    await flushPromises()
    expect(wb.currentVariantId).toBe(2)
    expect(api.getLatestTextJob).toHaveBeenCalledWith(2)
  })

  it('未完成任务的变体显示 loading', async () => {
    const { w, wb } = setup()
    wb.setVariantTask(2, { job_id: 10, status: 'running' })
    await w.vm.$nextTick()
    expect(w.findAll('.vpill')[1].find('.vpill__spinner').exists()).toBe(true)
  })

  it('当前变体胶囊有高亮 class', () => {
    const { w } = setup()
    const pills = w.findAll('.vpill')
    expect(pills[0].classes()).toContain('is-current')
    expect(pills[1].classes()).not.toContain('is-current')
  })

  it('无图变体显示占位「无图」', () => {
    const { w } = setup()
    const pills = w.findAll('.vpill')
    expect(pills[2].text()).toContain('无图')
  })

  it('删除胶囊：确认 → 调 api.deleteDraft → emit variant-deleted', async () => {
    const { w } = setup()
    const del = w.findAll('.vpill')[1].find('.vpill__del')
    await del.trigger('click')
    await flushPromises()
    expect(ElMessageBox.confirm).toHaveBeenCalled()
    expect(api.deleteDraft).toHaveBeenCalledWith(2)
    expect(w.emitted('variant-deleted')).toBeTruthy()
    expect(w.emitted('variant-deleted')[0]).toEqual([2])
  })

  it('取消删除不调 api、不 emit', async () => {
    ElMessageBox.confirm.mockRejectedValueOnce('cancel')
    const { w } = setup()
    const del = w.findAll('.vpill')[0].find('.vpill__del')
    await del.trigger('click')
    await flushPromises()
    expect(api.deleteDraft).not.toHaveBeenCalled()
    expect(w.emitted('variant-deleted')).toBeFalsy()
  })

  it('空态显示「暂无变体」', () => {
    setActivePinia(createPinia())
    const wb = useWorkbenchStore()
    wb.variants = []
    const w = mount(VariantGroupBar)
    expect(w.text()).toContain('暂无变体')
    expect(w.findAll('.vpill')).toHaveLength(0)
  })
})
