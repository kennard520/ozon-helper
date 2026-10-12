import { describe, it, expect } from 'vitest'
import bridge from '../common/bridge.js'

describe('explicit backend selection', () => {
  it('local mode never probes the remote backend', () => {
    expect(bridge.connectionBases('local')).toEqual(bridge.candidateBases())
  })
  it('remote mode keeps the existing backend', () => {
    expect(bridge.connectionBases('remote')).toEqual([bridge.PROD_BASE])
  })
  it('an explicit address never falls back to another backend', () => {
    expect(bridge.connectionBases('local', 'http://127.0.0.1:8787/')).toEqual(['http://127.0.0.1:8787'])
  })
  it('downloads local images from the backend rather than extension origin', () => {
    expect(bridge.mediaDownloadUrl('/media/draft-1/a.png', 'http://127.0.0.1:8585')).toBe('http://127.0.0.1:8585/media/draft-1/a.png')
    expect(bridge.mediaDownloadUrl('https://cdn.example/a.jpg', 'http://127.0.0.1:8585')).toBe('https://cdn.example/a.jpg')
  })
})
