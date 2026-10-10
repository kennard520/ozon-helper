import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import DraftListPane from './DraftListPane.vue'

const drafts = [
  { id: 1, source_title: '保温杯', source_platform: '1688', price: 38, status: 'ready', images: ['a.jpg'] },
  { id: 2, ozon_title: 'Кружка', source_platform: 'ozon', price: 99, status: 'published', images: [] },
]
const counts = { all: 2, invalid: 0, ready: 1, failed: 0, published: 1 }
function mountPane(props = {}) {
  return mount(DraftListPane, {
    props: { drafts, counts, filter: 'all', selectedId: null, warehouses: [], total: 2, page: 1, pageSize: 20, ...props },
    global: { plugins: [ElementPlus] },
  })
}
describe('DraftListPane', () => {
  it('渲染草稿卡 + 状态/来源标签', () => {
    const w = mountPane()
    expect(w.text()).toContain('保温杯'); expect(w.text()).toContain('Кружка')
    expect(w.text()).toContain('待发布'); expect(w.text()).toContain('已发布')
    expect(w.text()).toContain('1688')
  })
  it('点卡 emit select', async () => {
    const w = mountPane()
    await w.find('.dcard').trigger('click')
    expect(w.emitted('select')[0]).toEqual([1])
  })
  it('切 tab emit update:filter', async () => {
    const w = mountPane()
    const tab = w.findAll('.s-tabs__item').find(t => t.text().includes('已发布'))
    await tab.trigger('click')
    expect(w.emitted('update:filter')[0]).toEqual(['published'])
  })
})
