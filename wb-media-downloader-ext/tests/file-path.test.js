import { describe, expect, it } from 'vitest'
import Path from '../common/file-path.js'

describe('Windows-safe download paths', () => {
  it('removes Windows-invalid names, trailing dots, and reserved devices', () => {
    expect(Path.sanitizeSegment('红色:42/44. ')).toBe('红色_42_44')
    expect(Path.sanitizeSegment('CON')).toBe('_CON')
    expect(Path.sanitizeSegment('lpt9.txt')).toBe('_lpt9.txt')
  })

  it('stays Windows-safe when device protection is truncated at the length limit', () => {
    const segment = Path.sanitizeSegment(`CON.${'a'.repeat(74)}.x`, '未命名')

    expect(segment).not.toBe('')
    expect(segment.length).toBeLessThanOrEqual(80)
    expect(segment).not.toMatch(/[ .]$/)
    expect(segment).not.toMatch(/^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$/i)
  })

  it('preserves Chinese text, falls back when empty, and limits a segment to 80 characters', () => {
    expect(Path.sanitizeSegment('夏季连衣裙')).toBe('夏季连衣裙')
    expect(Path.sanitizeSegment('... ', '未命名')).toBe('未命名')
    expect(Path.sanitizeSegment('裙'.repeat(81))).toBe('裙'.repeat(80))
  })

  it('formats a stable local batch timestamp', () => {
    expect(Path.formatBatchTime(new Date(2026, 6, 14, 15, 30, 9))).toBe('20260714-153009')
  })

  it('extracts a lowercase URL extension and uses a safe fallback when absent', () => {
    expect(Path.extensionFromUrl('https://a.wbbasket.ru/image/photo.JPEG?size=big#hero', 'webp')).toBe('jpeg')
    expect(Path.extensionFromUrl('https://a.wbbasket.ru/image/no-extension?format=png', 'webp')).toBe('webp')
    expect(Path.extensionFromUrl('not a URL', 'MP4')).toBe('mp4')
  })
})
