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

  it('断点（下单为0）红色高亮 + 备注', () => {
    const gt = { ...GT, exposure: 12000, sessions: 800, cart: 120, ordered_units: 0 }
    const w = mount(ConversionFunnel, { props: { grandTotal: gt } })
    expect(w.text()).toContain('无成交')
    expect(w.find('.funnel__step.is-break').exists()).toBe(true)
    expect(w.text()).toContain('找到断点')
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

  it('GMV 用 ₽（卢布）不用 ¥', () => {
    const w = mount(KpiCards, { props: { grandTotal: GT } })
    expect(w.text()).toContain('₽')
    expect(w.text()).not.toContain('¥')
  })

  it('GMV/下单 为 0 时危险态', () => {
    const gt = { ...GT, revenue: 0, ordered_units: 0 }
    const w = mount(KpiCards, { props: { grandTotal: gt } })
    expect(w.find('.s-stat__v.is-danger').exists()).toBe(true)
  })

  it('加购转化极低时危险态', () => {
    const gt = { ...GT, conv_cart_pct: 0 }
    const w = mount(KpiCards, { props: { grandTotal: gt } })
    expect(w.find('.s-stat__v.is-danger').exists()).toBe(true)
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

  it('「仅看问题商品」筛选（按钮，含计数）', async () => {
    const w = mount(ProductTable, { props: { rows } })
    const btn = w.find('.pt__problem-btn')
    expect(btn.text()).toContain('1') // 1 个问题商品
    await btn.trigger('click')
    // 只有 row 102 有 diagnostics
    expect(w.text()).toContain('商品B')
    expect(w.text()).not.toContain('商品A')
  })

  it('列表头排序：点击曝光列在 desc↔asc 循环', async () => {
    const w = mount(ProductTable, { props: { rows } })
    const headers = w.findAll('.pt__th-sort')
    // 默认按曝光降序：商品A(500) 在 商品B(0) 之前
    let bodyText = w.findAll('tbody tr')[0].text()
    expect(bodyText).toContain('商品A')
    // 找到「曝光」表头点击 → 切到 asc
    const expHeader = headers.find(h => h.text().includes('曝光'))
    await expHeader.trigger('click')
    bodyText = w.findAll('tbody tr')[0].text()
    expect(bodyText).toContain('商品B') // asc：0 在前
  })

  it('没有商品链接时点击行不会打开草稿', async () => {
    const w = mount(ProductTable, { props: { rows } })
    const trs = w.findAll('tbody tr')
    await trs[0].trigger('click')
    expect(w.emitted('open-draft')).toBeFalsy()
    expect(w.find('.pt__title-link').exists()).toBe(false)
  })

  it('有商品链接时商品名称跳转 Ozon 详情', () => {
    const w = mount(ProductTable, {
      props: {
        rows: [{ ...rows[0], product_url: 'https://www.ozon.ru/product/101/' }],
      },
    })
    const link = w.find('.pt__title-link')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('https://www.ozon.ru/product/101/')
    expect(link.attributes('target')).toBe('_blank')
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

  it('显示搜索词实际查询日期', () => {
    const w = mount(KeywordInsight, {
      props: { bySku, dateFrom: '2026-06-01', dateTo: '2026-06-27', dateAdjusted: true },
    })
    expect(w.text()).toContain('2026-06-01 ~ 2026-06-27')
    expect(w.text()).toContain('T+3')
  })

  it('每行末尾渲染判定标签 + GMV 用 ₽', () => {
    const w = mount(KeywordInsight, { props: { bySku } })
    // 玻璃杯有订单 → 已覆盖；红茶杯高搜索零订单 → 污染词
    expect(w.text()).toContain('已覆盖')
    expect(w.text()).toContain('污染词')
    expect(w.text()).toContain('₽')
    expect(w.text()).not.toContain('¥')
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

  it('全部商品无曝光时显示核心诊断卡', () => {
    const gt = { ...GT, sku_with_traffic: 0 }
    const w = mount(DiagnosticBanner, { props: { grandTotal: gt, degraded: false } })
    expect(w.text()).toContain('零曝光')
    expect(w.find('.db').exists()).toBe(true)
  })

  it('核心诊断卡内嵌具体数字 + 排查清单', () => {
    const gt = { ...GT, sku_with_traffic: 0 }
    const w = mount(DiagnosticBanner, { props: { grandTotal: gt, degraded: false } })
    expect(w.text()).toContain('会话率')
    expect(w.text()).toContain('排查清单')
    expect(w.text()).toContain('搜索词洞察')
  })

  it('正常数据时不渲染核心诊断卡', () => {
    const gt = { ...GT, sku_with_traffic: 3, ordered_units: 10, conv_cart_pct: 15 }
    const w = mount(DiagnosticBanner, { props: { grandTotal: gt, degraded: false } })
    expect(w.find('.db').exists()).toBe(false)
    expect(w.find('.s-alert').exists()).toBe(false)
  })
})
