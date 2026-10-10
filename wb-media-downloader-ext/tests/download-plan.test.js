import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { describe, expect, it } from 'vitest'
import Plan from '../common/download-plan.js'

describe('deterministic WB download plans', () => {
  it('creates isolated gallery and video folders per variant', () => {
    const items = Plan.buildDownloadPlan(
      { title: '连衣裙', imtId: '1390661929' },
      [{
        nm: '1190575806',
        label: '黑色',
        gallery: ['https://a.wbbasket.ru/1190575806/1.webp'],
        rich: [],
        videos: ['https://v.wbbasket.ru/1190575806/1.mp4']
      }],
      new Date(2026, 6, 14, 15, 30, 9)
    )
    expect(items.map((item) => item.filename)).toEqual([
      'WB下载/连衣裙_imt-1390661929/20260714-153009/01_黑色_nm-1190575806/轮播图/01.jpg',
      'WB下载/连衣裙_imt-1390661929/20260714-153009/01_黑色_nm-1190575806/视频/01.mp4'
    ])
    expect(items[0].convertTo).toBe('jpg')
    expect(items[1].convertTo).toBe('')
  })

  it('keeps variant and source order while de-duplicating URLs with stable IDs', () => {
    const first = 'https://a.wbbasket.ru/1190575806/first.jpg?x=1'
    const second = 'https://a.wbbasket.ru/1190575806/second.webp'
    const items = Plan.buildDownloadPlan(
      { title: '连衣裙', imtId: '1390661929' },
      [
        { nm: '1190575806', label: '黑色', gallery: [first, first, second], rich: [], videos: [] },
        { nm: '1190575807', label: '白色', gallery: ['https://a.wbbasket.ru/1190575807/1.webp'], rich: [], videos: [] }
      ],
      new Date(2026, 6, 14, 15, 30, 9)
    )

    expect(items.map(({ id, nm, kind, url, status, attempts, error }) => ({
      id, nm, kind, url, status, attempts, error
    }))).toEqual([
      { id: '1190575806:gallery:1', nm: '1190575806', kind: 'gallery', url: first, status: 'pending', attempts: 0, error: '' },
      { id: '1190575806:gallery:2', nm: '1190575806', kind: 'gallery', url: second, status: 'pending', attempts: 0, error: '' },
      { id: '1190575807:gallery:1', nm: '1190575807', kind: 'gallery', url: 'https://a.wbbasket.ru/1190575807/1.webp', status: 'pending', attempts: 0, error: '' }
    ])
    expect(items.map((item) => item.filename)).toEqual([
      'WB下载/连衣裙_imt-1390661929/20260714-153009/01_黑色_nm-1190575806/轮播图/01.jpg',
      'WB下载/连衣裙_imt-1390661929/20260714-153009/01_黑色_nm-1190575806/轮播图/02.jpg',
      'WB下载/连衣裙_imt-1390661929/20260714-153009/02_白色_nm-1190575807/轮播图/01.jpg'
    ])
  })

  it('uses suffix-aware budgets so final path segments stay within 80 characters', () => {
    const nm = '1190575806'
    const imtId = '1390661929'
    const title = '产'.repeat(80)
    const label = '色'.repeat(80)
    const items = Plan.buildDownloadPlan(
      { title, imtId },
      [{
        nm,
        label,
        gallery: ['https://a.wbbasket.ru/1190575806/1.webp'],
        rich: [],
        videos: []
      }],
      new Date(2026, 6, 14, 15, 30, 9)
    )

    expect(items).toHaveLength(1)
    expect(items[0].id).toBe(`${nm}:gallery:1`)
    expect(items[0].nm).toBe(nm)
    expect(items[0].filename.length).toBeLessThanOrEqual(220)
    expect(items[0].filename.split('/').every((segment) => segment.length <= 80)).toBe(true)
    expect(items[0].filename).toBe(
      `WB下载/${'产'.repeat(65)}_imt-${imtId}/20260714-153009/01_${'色'.repeat(63)}_nm-${nm}/轮播图/01.jpg`
    )
    expect(items[0].filename.endsWith(`_nm-${nm}/轮播图/01.jpg`)).toBe(true)
  })

  it('rejects stable product or variant suffixes that cannot fit without truncating IDs', () => {
    const date = new Date(2026, 6, 14, 15, 30, 9)
    expect(() => Plan.buildDownloadPlan(
      { title: '连衣裙', imtId: '1'.repeat(76) },
      [],
      date
    )).toThrow(/imtId.*80/)
    expect(() => Plan.buildDownloadPlan(
      { title: '连衣裙', imtId: '1390661929' },
      [{ nm: '1'.repeat(77), label: '黑色', gallery: ['https://a.wbbasket.ru/1/1.webp'] }],
      date
    )).toThrow(/nm.*80/)
  })

  it('builds a deterministic batch root from sanitized product data', () => {
    expect(Plan.buildBatchRoot(
      { title: '连衣裙:夏季. ', imtId: '1390661929' },
      new Date(2026, 6, 14, 15, 30, 9)
    )).toBe('WB下载/连衣裙_夏季_imt-1390661929/20260714-153009')
  })

  it('loads browser UMD globals in manifest order and can build a plan', () => {
    const manifest = JSON.parse(readFileSync(new URL('../manifest.json', import.meta.url), 'utf8'))
    const scripts = manifest.content_scripts[0].js
    const pathIndex = scripts.indexOf('common/file-path.js')
    const planIndex = scripts.indexOf('common/download-plan.js')
    expect(pathIndex).toBeGreaterThanOrEqual(0)
    expect(planIndex).toBeGreaterThan(pathIndex)

    const context = { URL }
    runInNewContext(readFileSync(new URL('../common/file-path.js', import.meta.url), 'utf8'), context)
    runInNewContext(readFileSync(new URL('../common/download-plan.js', import.meta.url), 'utf8'), context)

    expect(context.WbMediaPath.sanitizeSegment('红色:42')).toBe('红色_42')
    expect(context.WbDownloadPlan.buildBatchRoot(
      { title: '连衣裙', imtId: '1390661929' },
      new Date(2026, 6, 14, 15, 30, 9)
    )).toBe('WB下载/连衣裙_imt-1390661929/20260714-153009')
  })
})
