import { it, expect } from 'vitest'
import vm from 'node:vm'
import { readFileSync } from 'node:fs'
import bridge from '../common/bridge.js'
import media from '../common/media-upload.js'

it('lite background uses seller upload and preserves original local URL in callback', async () => {
  const updates = []
  const ctx = vm.createContext({
    URL, AbortController, setTimeout, clearTimeout,
    importScripts() {},
    chrome: {
      storage: { local: { get: async () => ({ ozon_backend_mode: 'local', ozon_jwt: 'test-token' }) } },
      runtime: { onMessage: { addListener() {} } },
    },
    fetch: async (url, opts) => {
      if (url.endsWith('/api/ext/ping')) return { ok: true, json: async () => ({ local_lite: true }) }
      if (url.endsWith('/api/auth/me')) return { ok: true, json: async () => ({ user: { id: 1 } }) }
      if (url.endsWith('/api/ext/pending-media-drafts')) return { ok: true, json: async () => ({ drafts: [{ id: 9, images: ['/media/a.png', 'https://ir.ozone.ru/b.jpg'] }] }) }
      if (url.endsWith('/api/ext/update-draft-media')) {
        updates.push(JSON.parse(opts.body)); return { ok: true }
      }
      throw new Error('Unexpected request: ' + url)
    },
  })
  ctx.self = ctx
  ctx.OzonHelperBridge = bridge
  ctx.OzonHelperMedia = media
  vm.runInContext(readFileSync(new URL('../background.js', import.meta.url), 'utf8'), ctx)
  vm.runInContext(`uploadMedia = async (urls) => ({ map: Object.fromEntries(urls.map(u => [u, 'https://ir.ozone.ru/uploaded.jpg'])) }); uploadMediaOss = async () => { throw new Error('OSS must not be required') }`, ctx)
  await vm.runInContext('rehostPending()', ctx)
  expect(updates).toEqual([{ draft_id: 9, media_map: { '/media/a.png': 'https://ir.ozone.ru/uploaded.jpg' } }])
})
