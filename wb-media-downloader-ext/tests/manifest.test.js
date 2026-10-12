import { describe, expect, it } from 'vitest'
import fs from 'node:fs'

const manifest = JSON.parse(fs.readFileSync(new URL('../manifest.json', import.meta.url), 'utf8'))

describe('manifest security boundary', () => {
  it('uses readable UTF-8 Chinese metadata in Chrome UI', () => {
    expect(manifest.name).toBe('WB 图片视频下载器')
    expect(manifest.description).toBe('一键下载 WB 商品轮播图和视频')
    expect(manifest.action.default_title).toBe('WB 图片视频下载器')
  })

  it('is WB-only and requests no backend or account permissions', () => {
    expect(manifest.manifest_version).toBe(3)
    expect(manifest.permissions.sort()).toEqual(['downloads', 'storage'])
    expect(manifest.host_permissions).toEqual([
      'https://www.wildberries.ru/*',
      'https://*.wbbasket.ru/*',
      'https://*.geobasket.ru/*',
      'https://*.wb.ru/*'
    ])
    expect(JSON.stringify(manifest)).not.toMatch(/ozon|1688|localhost|<all_urls>|cookies|tabs/i)
    expect(manifest.content_scripts[0].matches).toEqual([
      'https://www.wildberries.ru/catalog/*/detail.aspx*'
    ])
  })
})
