import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

// stub EP / problematic components — only if needed
// Lightweight components rely on SBadge / SStatCard (pure divs) — no EP usage so no stub needed

import ConversionFunnel from './ConversionFunnel.vue'
import KpiCards from './KpiCards.vue'
import ProductTable from './ProductTable.vue'
import TrafficTrend from './TrafficTrend.vue'
import KeywordInsight from './KeywordInsight.vue'
import DiagnosticBanner from './DiagnosticBanner.vue'

const GT = {
  sku_count: 3, exposure: 12000, sessions: 800, cart: 120, ordered_units: 30,
  revenue: 15000, conv_cart_pct: 15, sku_with_traffic: 2,
}

describe('ConversionFunnel', () => {
  it('渲染四段漏斗标签', () => {
    const w = mount(ConversionFunnel, { props: { grandTotal: GT } })
    expect(w.text()).toContain('曝光')
    expect(w.text()).toContain('访问')
    expect(w.text()).toContain('加购')
    expect(w.text()).toContain('下单')
  })

  it('无数据显示占位', () => {
    const w = mount(ConversionFunnel, { props: { grandTotal: null } })
    expect(w.text()).toContain('暂无数据')
  })

  it('大数格式化为万', () => {
    const w = mount(ConversionFunnel, { props: { grandTotal: { ...GT, exposure: 120000 } } })
    expect(w.text()).toContain('12.0万')
  })
})

describe('KpiCards', () => {
  it('渲染四张 KPI 卡片', () => {
    const w = mount(KpiCards, { props: { grandTotal: GT } })
    expect(w.text()).toContain('总曝光')
    expect(w.text()).toContain('总访问')
    expect(w.text()).toContain('加购转化')
    expect(w.text()).toContain('GMV')
  })

  it('null 时显示占位', () => {
    const w = mount(KpiCards, { props: { grandTotal: null } })
    expect(w.text()).toContain('暂无汇总数据')
  })
})

describe('ProductTable', () => {
  const rows = [
    { sku: 101, offer_id: 'A', title: '商品A', price: 100, stock: 5, exposure: 500, sessions: 100, cart: 20, conv_cart_pct: 4, ordered_units: 5, revenue: 500, diagnostics: [] },
    { sku: 102, offer_id: 'B', title: '商品B', price: 200, stock: 0, exposure: 0, sessions: 0, cart: 0, conv_cart_pct: 0, ordered_units: 0, revenue: 0, diagnostics: ['缺货', '0曝光'] },
  ]

  it('渲染商品行', () => {
    const w = mount(ProductTable, { props: { rows } })
    expect(w.text()).toContain('商品A')
    expect(w.text()).toContain('商品B')
  })

  it('诊断标签渲染为 badge', () => {
    const w = mount(ProductTable, { props: { rows } })
    expect(w.text()).toContain('缺货')
    expect(w.text()).toContain('0曝光')
  })

  it('「仅看问题商品」筛选', async () => {
    const w = mount(ProductTable, { props: { rows } })
    const checkbox = w.find('input[type="checkbox"]')
    await checkbox.setValue(true)
    // 只有 row 102 有 diagnostics
    expect(w.text()).toContain('商品B')
    expect(w.text()).not.toContain('商品A')
  })

  it('点击行 emit open-draft', async () => {
    const w = mount(ProductTable, { props: { rows } })
    const trs = w.findAll('tbody tr')
    await trs[0].trigger('click')
    expect(w.emitted('open-draft')).toBeTruthy()
    expect(w.emitted('open-draft')[0][0].sku).toBe(101)
  })
})

describe('TrafficTrend', () => {
  const trafficRows = [
    { sku: 101, day: '2026-06-25', hits_view: 200, session_view: 80, hits_tocart: 20, ordered_units: 5 },
    { sku: 101, day: '2026-06-26', hits_view: 300, session_view: 100, hits_tocart: 30, ordered_units: 8 },
  ]

  it('渲染图例和柱子', () => {
    const w = mount(TrafficTrend, { props: { rows: trafficRows } })
    expect(w.text()).toContain('曝光')
    expect(w.text()).toContain('访问')
    expect(w.text()).toContain('加购')
    // 日期标签
    expect(w.text()).toContain('06-25')
    expect(w.text()).toContain('06-26')
  })

  it('空数据显示提示', () => {
    const w = mount(TrafficTrend, { props: { rows: [] } })
    expect(w.text()).toContain('暂无流量趋势数据')
  })

  it('按 day 聚合多 sku 数据', () => {
    const rows = [
      { sku: 101, day: '2026-06-25', hits_view: 100, session_view: 40, hits_tocart: 10, ordered_units: 2 },
      { sku: 102, day: '2026-06-25', hits_view: 150, session_view: 60, hits_tocart: 15, ordered_units: 3 },
    ]
    const w = mount(TrafficTrend, { props: { rows } })
    // 同一天 → 一个 bar group
    const barGroups = w.findAll('.tt__bar-group')
    expect(barGroups.length).toBe(1)
  })
})

describe('KeywordInsight', () => {
  const bySku = {
    '101': [
      { query: '红茶杯', searches: 1000, ctr: 0.02, position: 5, orders: 0, gmv: 0 },
      { query: '玻璃杯', searches: 800, ctr: 0.08, position: 2, orders: 5, gmv: 500 },
    ]
  }

  it('渲染三分类卡片', () => {
    const w = mount(KeywordInsight, { props: { bySku } })
    expect(w.text()).toContain('机会词')
    expect(w.text()).toContain('污染词')
    expect(w.text()).toContain('已覆盖')
  })

  it('渲染词表', () => {
    const w = mount(KeywordInsight, { props: { bySku } })
    expect(w.text()).toContain('红茶杯')
    expect(w.text()).toContain('玻璃杯')
  })

  it('空时显示提示', () => {
    const w = mount(KeywordInsight, { props: { bySku: {} } })
    expect(w.text()).toContain('暂无搜索词数据')
  })
})

describe('DiagnosticBanner', () => {
  it('degraded=true 显示降级提示', () => {
    const w = mount(DiagnosticBanner, { props: { grandTotal: GT, degraded: true } })
    expect(w.text()).toContain('降级')
  })

  it('全部商品无曝光时显示洞察', () => {
    const gt = { ...GT, sku_with_traffic: 0 }
    const w = mount(DiagnosticBanner, { props: { grandTotal: gt, degraded: false } })
    expect(w.text()).toContain('无曝光')
  })

  it('正常数据时不渲染 alert', () => {
    const gt = { ...GT, sku_with_traffic: 3, ordered_units: 10, conv_cart_pct: 15 }
    const w = mount(DiagnosticBanner, { props: { grandTotal: gt, degraded: false } })
    // 没有 warn/danger alert
    expect(w.find('.s-alert').exists()).toBe(false)
  })
})
