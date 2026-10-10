import { describe, expect, it } from 'vitest'
import fs from 'node:fs'

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), 'utf8')

describe('content script contract', () => {
  it('collects only bounded card/video resource hints and sends known actions', () => {
    const source = read('../content/downloader.js')
    expect(source).toContain("performance.getEntriesByType('resource')")
    expect(source).toContain('START_JOB')
    expect(source).toContain('STOP_JOB')
    expect(source).toContain('RETRY_FAILED')
    expect(source).toContain('GET_JOB_STATE')
    expect(source).toContain('OPEN_DOWNLOAD')
    expect(source).toMatch(/slice\(-100\)/)
    expect(source).toMatch(/cardUrl:\s*cardUrl\(\),\s*resourceUrls:\s*resourceUrls\(\)/)
    expect(source).not.toMatch(/querySelectorAll\(['"]img|feedback|recommendation/i)
  })

  it('guards startup and runtime states to the current nm and handles navigation', () => {
    const source = read('../content/downloader.js')
    expect(source).toMatch(/state\.nm\s*={2,3}\s*nm/)
    expect(source).toContain('JOB_STATE')
    expect(source).toContain('pushState')
    expect(source).toContain('replaceState')
    expect(source).toContain('popstate')
    expect(source).toContain('destroy')
  })

  it('keeps every CSS selector scoped to the panel root', () => {
    const css = read('../content/downloader.css')
    expect(css).toContain('#wb-media-downloader')
    expect(css).toContain('right: 20px')
    expect(css).toContain('bottom: 20px')
    expect(css).toContain('z-index: 2147483647')
    expect(css).toContain('width: 320px')
    expect(css).toContain('border-radius: 12px')
    expect(css).toContain('@media (max-width: 480px)')
    const selectors = css
      .split('{')
      .slice(0, -1)
      .map((chunk) => chunk.split('}').pop().trim())
      .flatMap((chunk) => chunk.split(',').map((selector) => selector.trim()))
      .filter(Boolean)
      .filter((selector) => !selector.startsWith('@'))
    expect(selectors.every((selector) => selector.startsWith('#wb-media-downloader'))).toBe(true)
  })

  it('worker opens last completed download or default folder under existing sender checks', () => {
    const source = read('../service-worker.js')
    expect(source).toContain('OPEN_DOWNLOAD')
    expect(source).toContain('chrome.downloads.show')
    expect(source).toContain('chrome.downloads.showDefaultFolder')
    expect(source).toMatch(/isProductPage\(sender\.url/)
  })
})
