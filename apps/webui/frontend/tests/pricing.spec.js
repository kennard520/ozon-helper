import { describe, it, expect } from 'vitest'
import { solvePrice } from '../src/utils/pricing.js'
import { OZON_REALFBS_DATA } from '../src/utils/pricingData.js'

// 表征测试：用真实类目 + 真实 routes 锁定移植前后的数值，证明逐字移植没有漂移。
// 输入对象字段严格对齐 static/pricing.js readInput() 产出的形状。
describe('solvePrice', () => {
  const cat = OZON_REALFBS_DATA.categories.find((c) => c.subEn === 'Decor, Cleaning & Storage')
  const input = {
    costCny: 20,
    weightG: 300,
    lengthCm: 20,
    widthCm: 15,
    heightCm: 10,
    marginTargetPct: 30,
    adPct: 0,
    strategy: 'balanced',
    rubCny: 0.0927,
    paymentPct: 0.4,
    returnReservePct: 3,
    lossReservePct: 2,
    packingCny: 3,
    domesticShipCny: 0,
    otherFixedCny: 0,
    hasBattery: false,
    isLiquid: false,
  }

  it('给定输入产出自洽的价格/利润/计费重并锁定数值', () => {
    const r = solvePrice(input, OZON_REALFBS_DATA.routes, cat)

    // 结构不变量（仅断言真实返回里存在的字段）
    expect(r).not.toBeNull()
    expect(r.targetRub).toBeGreaterThan(0)
    expect(r.bestRoute).toBeTruthy()
    expect(r.availableRoutes.length).toBeGreaterThan(0)
    expect(r.profitCny).toBeGreaterThan(0)
    expect(r.margin).toBeGreaterThan(0)
    // 计费重：实重 300g、未走体积重，billable 应 >= 物理重
    expect(r.chargeable.billable).toBeGreaterThanOrEqual(r.chargeable.physical)
    expect(r.chargeable.billable).toBeGreaterThanOrEqual(input.weightG)
    // 佣金落在所选类目的 rfbs 区间内
    expect(cat.rfbs).toContain(r.commission)
    // 划线价 = 销售价 / 0.8（移植自原公式）
    expect(r.linePriceRub).toBeGreaterThan(r.targetRub)

    // 锁定真实捕获值（移植 = 1:1，任何漂移都会让以下断言失败）
    expect(Math.round(r.targetRub)).toBe(557)
    expect(Math.round(r.linePriceRub)).toBe(696)
    expect(r.commission).toBe(0.12)
    expect(r.tierIndex).toBe(0)
    expect(Math.round(r.chargeable.billable)).toBe(300)
    expect(Number(r.targetCny.toFixed(4))).toBe(51.6223)
    expect(Number(r.profitCny.toFixed(2))).toBe(9.84)
    expect(r.availableRoutes.length).toBe(26)
    expect(r.bestRoute.provider).toBe('ATC')
    expect(r.bestRoute.serviceLevel).toBe('Economy')
  })
})
