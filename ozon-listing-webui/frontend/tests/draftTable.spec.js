import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, it, expect } from 'vitest'
import DraftTable from '../src/components/DraftTable.vue'

const drafts = [
  { id: 1, ozon_title: 'Шлем', source_title: '头盔', source_platform: '1688',
    source_url: 'https://detail.1688.com/offer/9.html', purchase_url: '', warehouse_id: 7, stock: 3, status: 'ready' },
  { id: 2, ozon_title: 'Zap', source_title: '配件', source_platform: 'ozon',
    purchase_url: '', warehouse_id: null, stock: 0, status: 'published', source: 'ozon' },
]
const warehouses = [{ warehouse_id: 7, name: '成都仓' }]

function mountTable() {
  return mount(DraftTable, {
    props: { drafts, counts: { all: 2 }, filter: 'all', warehouses },
    global: { plugins: [ElementPlus] },
  })
}

describe('DraftTable.vue', () => {
  it('warehouse_id 映射成仓库名；无仓库显示 -', () => {
    const vm = mountTable().vm
    expect(vm.warehouseName(7)).toBe('成都仓')
    expect(vm.warehouseName(null)).toBe('-')
    expect(vm.warehouseName(99)).toBe('#99')
  })

  it('采购链接：1688 回退 source_url，Ozon 无链接返回空', () => {
    const vm = mountTable().vm
    expect(vm.purchaseLink(drafts[0])).toBe('https://detail.1688.com/offer/9.html')
    expect(vm.purchaseLink(drafts[1])).toBe('')
  })

  it('批量设置库存 emit batch-update 带选中 ids 和 patch', async () => {
    const w = mountTable()
    w.vm.checked = drafts
    w.vm.batchStock = 50
    w.vm.applyStock()
    const ev = w.emitted('batch-update')
    expect(ev).toBeTruthy()
    expect(ev[0][0]).toEqual({ ids: [1, 2], patch: { stock: 50 } })
  })

  it('批量设置仓库 emit batch-update 带 warehouse_id', async () => {
    const w = mountTable()
    w.vm.checked = [drafts[0]]
    w.vm.batchWarehouse = 7
    w.vm.applyWarehouse()
    const ev = w.emitted('batch-update')
    expect(ev[0][0]).toEqual({ ids: [1], patch: { warehouse_id: 7 } })
  })
})
