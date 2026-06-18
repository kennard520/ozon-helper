import { describe, it, expect } from 'vitest'
import OzonHelperMedia from '../common/media-upload.js'

const { isOzonCdn, collectMediaUrls, applyMediaMap, parseCompanyId } = OzonHelperMedia

describe('parseCompanyId', () => {
  it('从 cookie 串扫出 companyId', () => {
    expect(parseCompanyId('x=1; companyId=5020196; y=2')).toBe('5020196')
    expect(parseCompanyId('a=b; company_id=12345678')).toBe('12345678')
  })
  it('URL 编码的 cookie 也能扫', () => {
    expect(parseCompanyId('state=%7B%22companyId%22%3A%225020196%22%7D')).toBe('5020196')
  })
  it('没有则 null', () => {
    expect(parseCompanyId('a=b; c=d')).toBeNull()
    expect(parseCompanyId('')).toBeNull()
  })
})

describe('isOzonCdn', () => {
  it('Ozon 自家 CDN 判 true', () => {
    expect(isOzonCdn('https://ir.ozone.ru/s3/x/y.jpg')).toBe(true)
    expect(isOzonCdn('https://cdn1.ozone.ru/a.jpg')).toBe(true)
  })
  it('非 Ozon CDN 判 false', () => {
    expect(isOzonCdn('https://cbu01.alicdn.com/img/x.jpg')).toBe(false)
    expect(isOzonCdn('')).toBe(false)
  })
})

describe('collectMediaUrls', () => {
  it('收集全部媒体(含 Ozon 图)、去重、含富文本内嵌图与视频', () => {
    const data = {
      images: ['https://ir.ozone.ru/keep.jpg', 'https://cbu01.alicdn.com/a.jpg', 'https://cbu01.alicdn.com/a.jpg'],
      detail_images: ['https://cbu01.alicdn.com/b.jpg'],
      video_url: 'https://cloud.video.taobao.com/x.mp4',
      rich_content_json: { content: [{ blocks: [{ img: { src: 'https://cbu01.alicdn.com/r1.jpg', srcMobile: 'https://ir.ozone.ru/r2.jpg' } }] }] }
    }
    const urls = collectMediaUrls(data)
    // 所有平台都要重传：竞品 Ozon 图也收
    expect(urls).toContain('https://ir.ozone.ru/keep.jpg')
    expect(urls).toContain('https://cbu01.alicdn.com/a.jpg')
    expect(urls).toContain('https://cbu01.alicdn.com/b.jpg')
    expect(urls).toContain('https://cloud.video.taobao.com/x.mp4')
    expect(urls).toContain('https://cbu01.alicdn.com/r1.jpg')
    expect(urls).toContain('https://ir.ozone.ru/r2.jpg')
    expect(urls.filter((u) => u === 'https://cbu01.alicdn.com/a.jpg').length).toBe(1) // 去重
  })
  it('无媒体 → 空', () => {
    expect(collectMediaUrls({ images: [] })).toEqual([])
    expect(collectMediaUrls({})).toEqual([])
  })
})

describe('applyMediaMap', () => {
  it('替换主图/详情图/视频/富文本内嵌图，不改原对象', () => {
    const data = {
      images: ['https://cbu01.alicdn.com/a.jpg', 'https://ir.ozone.ru/old.jpg'],
      detail_images: ['https://cbu01.alicdn.com/b.jpg'],
      video_url: 'https://cloud.video.taobao.com/x.mp4',
      rich_content_json: { blocks: [{ img: { src: 'https://cbu01.alicdn.com/r1.jpg' } }] }
    }
    const map = {
      'https://cbu01.alicdn.com/a.jpg': 'https://ir.ozone.ru/A.jpg',
      'https://ir.ozone.ru/old.jpg': 'https://ir.ozone.ru/NEW.jpg',
      'https://cbu01.alicdn.com/b.jpg': 'https://ir.ozone.ru/B.jpg',
      'https://cloud.video.taobao.com/x.mp4': 'https://ir.ozone.ru/V.mp4',
      'https://cbu01.alicdn.com/r1.jpg': 'https://ir.ozone.ru/R1.jpg'
    }
    const out = applyMediaMap(data, map)
    expect(out.images).toEqual(['https://ir.ozone.ru/A.jpg', 'https://ir.ozone.ru/NEW.jpg'])
    expect(out.detail_images).toEqual(['https://ir.ozone.ru/B.jpg'])
    expect(out.video_url).toBe('https://ir.ozone.ru/V.mp4')
    expect(out.rich_content_json.blocks[0].img.src).toBe('https://ir.ozone.ru/R1.jpg')
    // 原对象不被就地改坏
    expect(data.images[0]).toBe('https://cbu01.alicdn.com/a.jpg')
    expect(data.rich_content_json.blocks[0].img.src).toBe('https://cbu01.alicdn.com/r1.jpg')
  })
  it('无映射的链接原样保留', () => {
    const out = applyMediaMap({ images: ['https://x/u.jpg'] }, {})
    expect(out.images).toEqual(['https://x/u.jpg'])
  })
})
