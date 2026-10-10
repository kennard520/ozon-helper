import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import { runInNewContext } from 'node:vm'

async function waitUntil(assertion) {
  for (let index = 0; index < 20; index++) {
    try {
      assertion()
      return
    } catch (error) {
      if (index === 19) throw error
      await new Promise((resolve) => setTimeout(resolve, 0))
    }
  }
}

function workerContext(controllerOverrides = {}) {
  const onChangedListeners = []
  const onMessageListeners = []
  const controller = {
    start: async () => ({}),
    stop: async () => ({}),
    retryFailed: async () => ({}),
    getState: () => ({}),
    restore: async () => ({}),
    isActive: () => false,
    ...controllerOverrides
  }
  const context = {
    URL,
    Set,
    Promise,
    Number,
    String,
    Error,
    RegExp,
    console,
    AbortController,
    setTimeout,
    clearTimeout,
    importScripts: () => {},
    fetch: async () => ({ ok: true, status: 206, body: { cancel: async () => {} }, json: async () => ({}) }),
    WbMediaCard: {
      isAllowedCardUrl: () => false,
      isProductPage: (url) => /^https:\/\/www\.wildberries\.ru\/catalog\/\d+\/detail\.aspx/.test(url)
    },
    WbMediaResolver: {
      isAllowedMediaUrl: (url) => /^https:\/\/[^/]*\.(?:wbbasket|geobasket|wb)\.ru\/.+\.(?:mp4|webp|jpg|png|avif|gif)$/.test(url)
    },
    WbJobController: {
      createJobController: () => controller
    },
    chrome: {
      downloads: {
        onChanged: {
          addListener: (listener) => onChangedListeners.push(listener),
          removeListener: () => {}
        },
        download: async () => 1,
        cancel: async () => {},
        search: async () => [],
        show: async () => {},
        showDefaultFolder: () => {}
      },
      runtime: {
        onMessage: {
          addListener: (listener) => onMessageListeners.push(listener)
        }
      },
      storage: {
        session: {
          get: async () => ({}),
          set: async () => {}
        }
      },
      tabs: {
        query: async () => [],
        sendMessage: async () => {}
      }
    }
  }
  runInNewContext(fs.readFileSync(new URL('../service-worker.js', import.meta.url), 'utf8'), context)
  return { context, controller, onChangedListeners, onMessageListeners }
}

describe('WB media downloader service worker contract', () => {
  const source = () => fs.readFileSync(new URL('../service-worker.js', import.meta.url), 'utf8')

  it('keeps readable manifest metadata and bounded permissions', () => {
    const manifest = JSON.parse(fs.readFileSync(new URL('../manifest.json', import.meta.url), 'utf8'))
    expect(manifest.name).toBe('WB 图片视频下载器')
    expect(manifest.description).toBe('一键下载 WB 商品轮播图和视频')
    expect(manifest.action.default_title).toBe('WB 图片视频下载器')
    expect(manifest.permissions).not.toContain('tabs')
    expect(JSON.stringify(manifest)).not.toContain('<all_urls>')
  })

  it('imports only local modules and exposes the four bounded message types', () => {
    const text = source()
    expect(text).toContain('importScripts(')
    for (const type of ['START_JOB', 'STOP_JOB', 'RETRY_FAILED', 'GET_JOB_STATE']) expect(text).toContain(type)
    expect(text).not.toMatch(/collectParsed|openEditor|uploadMedia|localhost|ozon/i)
  })

  it('narrows sender, message type, and payload before reaching the controller', () => {
    const text = source()
    expect(text).toMatch(/isProductPage\(sender\.url/)
    expect(text).toMatch(/START_JOB/)
    expect(text).toMatch(/STOP_JOB/)
    expect(text).toMatch(/RETRY_FAILED/)
    expect(text).toMatch(/GET_JOB_STATE/)
    expect(text).toMatch(/resourceUrls[\s\S]*slice\(0,\s*100\)/)
    expect(text).toMatch(/isAllowedMediaUrl/)
    expect(text).not.toMatch(/controller\.start\(message\)/)
  })

  it('restores active saved jobs and reconciles on download wake events', () => {
    const text = source()
    expect(text).toMatch(/storage\.session\.get/)
    expect(text).toMatch(/wbMediaJob/)
    expect(text).toMatch(/restore\(/)
    expect(text).toMatch(/downloads\.onChanged\.addListener/)
    expect(text).toMatch(/reconcileDownload/)
  })

  it('bounds network probing and JSON fetches with AbortController timeouts', () => {
    const text = source()
    expect(text).toMatch(/AbortController/)
    expect(text).toMatch(/setTimeout/)
    expect(text).toMatch(/Range['"]?\s*:\s*['"]bytes=0-0/)
  })

  it('probe rejects non-WB media URLs before fetch', async () => {
    const { context } = workerContext({ isActive: () => true })
    let fetched = false
    context.fetch = async () => {
      fetched = true
      return { ok: true, status: 206, body: { cancel: async () => {} } }
    }

    await expect(context.probe('https://example.com/file.mp4')).rejects.toThrow('URL not allowed')
    expect(fetched).toBe(false)
  })

  it('download wake events do not restore while the live controller is active', async () => {
    let restoreCalls = 0
    let active = false
    let resolveStart
    const { onChangedListeners, onMessageListeners } = workerContext({
      isActive: () => active,
      start: async () => {
        active = true
        return new Promise((resolve) => { resolveStart = resolve })
      },
      restore: async () => {
        restoreCalls += 1
        return {}
      }
    })

    const responses = []
    onMessageListeners[0](
      { type: 'START_JOB', nm: '10', resourceUrls: ['https://basket-01.wbbasket.ru/vol0/part0/10/images/big/1.webp'] },
      { url: 'https://www.wildberries.ru/catalog/10/detail.aspx' },
      (response) => responses.push(response)
    )
    await waitUntil(() => expect(active).toBe(true))
    onChangedListeners[0]({ id: 1, state: { current: 'in_progress' } })
    await new Promise((resolve) => setTimeout(resolve, 0))
    resolveStart({})
    active = false
    await waitUntil(() => expect(responses).toHaveLength(1))

    expect(restoreCalls).toBe(0)
  })

  it('falls back to the default folder when the last completed download id is stale', async () => {
    let shownId = null
    let defaultFolderCalls = 0
    const { context, onChangedListeners, onMessageListeners } = workerContext({
      isActive: () => false,
      getState: () => ({ phase: 'complete' })
    })
    context.chrome.downloads.show = async (id) => {
      shownId = id
      throw new Error('download id not found')
    }
    context.chrome.downloads.showDefaultFolder = () => {
      defaultFolderCalls += 1
    }
    context.chrome.downloads.download = async () => 55

    const started = await context.startDownload({ url: 'https://example.invalid/file.webp', filename: 'file.webp' })
    onChangedListeners.forEach((listener) => listener({ id: 55, state: { current: 'complete' } }))
    await started.completion
    const responses = []
    onMessageListeners[0](
      { type: 'OPEN_DOWNLOAD' },
      { url: 'https://www.wildberries.ru/catalog/10/detail.aspx' },
      (response) => responses.push(response)
    )
    await waitUntil(() => expect(responses).toHaveLength(1))

    expect(shownId).toBe(55)
    expect(defaultFolderCalls).toBe(1)
    expect(responses[0]).toEqual({ ok: true, state: { phase: 'complete' } })
  })
})
