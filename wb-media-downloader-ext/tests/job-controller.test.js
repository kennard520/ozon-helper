import { describe, expect, it, vi } from 'vitest'
import Jobs from '../common/job-controller.js'

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

describe('WB media download job controller', () => {
  it('resolves every sibling separately and downloads one combined plan', async () => {
    const resolved = []
    const cards = {
      '10': {
        card: {
          nm_id: 10,
          imt_id: 99,
          imt_name: 'Dress',
          full_colors: [{ nm_id: 11 }],
          colors: [10],
          nm_colors_names: 'white',
          media: { photo_count: 1 }
        },
        cardUrl: 'https://basket-01.wbbasket.ru/vol0/part0/10/info/ru/card.json',
        host: 'basket-01.wbbasket.ru'
      },
      '11': {
        card: {
          nm_id: 11,
          imt_id: 99,
          imt_name: 'Dress',
          nm_colors_names: 'black',
          media: { photo_count: 1, has_video: true }
        },
        cardUrl: 'https://basket-01.wbbasket.ru/vol0/part0/11/info/ru/card.json',
        host: 'basket-01.wbbasket.ru'
      }
    }
    const emitted = []
    const controller = Jobs.createJobController({
      now: () => new Date(2026, 6, 14, 15, 30, 9),
      resolveCard: async (nm) => { resolved.push(nm); return cards[nm] },
      fetchJson: async (url) => url.endsWith('/rich_v1.json') ? { content: [] } : {},
      probe: async () => true,
      runQueue: async (items, options) => {
        items.forEach((item) => { item.status = 'complete' })
        options.onProgress({ total: items.length, completed: items.length, failed: 0, cancelled: 0, active: 0, items })
        return { items, completed: items.length, failed: 0, cancelled: 0 }
      },
      saveState: vi.fn(async () => {}),
      emitState: vi.fn(async (state) => { emitted.push(state) })
    })

    const final = await controller.start({ nm: '10', cardUrl: '', resourceUrls: [] })

    expect(resolved).toEqual(['10', '11'])
    expect(final.phase).toBe('complete')
    expect(final.totalVariants).toBe(2)
    expect(final.resolvedVariants).toBe(2)
    expect(final.totalFiles).toBeGreaterThan(0)
    expect(final.items.at(-1).filename).toContain('下载结果.json')
    expect(emitted.at(-1).phase).toBe('complete')
  })

  it('downloads result JSON after media queue with final media statuses', async () => {
    const queueCalls = []
    const controller = Jobs.createJobController({
      now: () => new Date(2026, 6, 14, 15, 30, 9),
      resolveCard: async () => ({
        card: { nm_id: 10, imt_id: 99, imt_name: 'Dress', media: { photo_count: 3 } },
        cardUrl: 'https://basket-01.wbbasket.ru/vol0/part0/10/info/ru/card.json',
        host: 'basket-01.wbbasket.ru'
      }),
      fetchJson: async () => ({ content: [] }),
      probe: async () => false,
      runQueue: async (items) => {
        queueCalls.push(items.map((item) => ({ id: item.id, url: item.url })))
        if (queueCalls.length === 1) {
          return {
            items: items.map((item, index) => ({
              ...item,
              status: ['complete', 'failed', 'cancelled'][index],
              error: index === 1 ? 'network' : ''
            })),
            completed: 1,
            failed: 1,
            cancelled: 1
          }
        }
        return {
          items: items.map((item) => ({ ...item, status: 'complete' })),
          completed: 1,
          failed: 0,
          cancelled: 0
        }
      },
      saveState: async () => {},
      emitState: async () => {}
    })

    const final = await controller.start({ nm: '10' })
    const resultDownload = final.items.at(-1)
    const resultPayload = JSON.parse(decodeURIComponent(resultDownload.url.split(',', 2)[1]))

    expect(queueCalls.map((call) => call.map((item) => item.id))).toEqual([
      ['10:gallery:1', '10:gallery:2', '10:gallery:3'],
      ['result']
    ])
    expect(resultPayload.items.map((item) => item.status)).toEqual(['complete', 'failed', 'cancelled'])
    expect(resultDownload.status).toBe('complete')
  })

  it('waits for delayed progress publishing before final complete state', async () => {
    let releaseProgress
    const savedPhases = []
    const controller = Jobs.createJobController({
      now: () => new Date(2026, 6, 14, 15, 30, 9),
      resolveCard: async () => ({
        card: { nm_id: 10, imt_id: 99, imt_name: 'Dress', media: { photo_count: 1 } },
        cardUrl: 'https://basket-01.wbbasket.ru/vol0/part0/10/info/ru/card.json',
        host: 'basket-01.wbbasket.ru'
      }),
      fetchJson: async () => ({ content: [] }),
      probe: async () => false,
      runQueue: async (items, options) => {
        options.onProgress({ total: items.length, completed: 0, failed: 0, cancelled: 0, active: 1, items })
        return { items: items.map((item) => ({ ...item, status: 'complete' })), completed: items.length, failed: 0, cancelled: 0 }
      },
      saveState: async (state) => {
        if (state.phase === 'downloading' && state.completed === 0 && !releaseProgress) {
          await new Promise((resolve) => { releaseProgress = resolve })
        }
        savedPhases.push(`${state.phase}:${state.completed}`)
      },
      emitState: async () => {}
    })

    const started = controller.start({ nm: '10' })
    await waitUntil(() => expect(releaseProgress).toBeTypeOf('function'))
    releaseProgress()
    await started
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(savedPhases.at(-1)).toMatch(/^complete:/)
  })

  it('records variant errors and continues resolving other variants', async () => {
    const controller = Jobs.createJobController({
      now: () => new Date(2026, 6, 14, 15, 30, 9),
      resolveCard: async (nm) => {
        if (nm === '11') throw new Error('missing card')
        return {
          card: {
            nm_id: Number(nm),
            imt_id: 99,
            imt_name: 'Dress',
            full_colors: nm === '10' ? [{ nm_id: 11 }, { nm_id: 12 }] : [],
            nm_colors_names: `color-${nm}`,
            media: { photo_count: 1 }
          },
          cardUrl: `https://basket-01.wbbasket.ru/vol0/part0/${nm}/info/ru/card.json`,
          host: 'basket-01.wbbasket.ru'
        }
      },
      fetchJson: async () => { throw new Error('404') },
      probe: async () => false,
      runQueue: async (items, options) => {
        options.onProgress({ total: items.length, completed: 0, failed: 0, cancelled: 0, active: 0, items })
        return { items, completed: 0, failed: 0, cancelled: 0 }
      },
      saveState: async () => {},
      emitState: async () => {}
    })

    const final = await controller.start({ nm: '10' })

    expect(final.phase).toBe('complete')
    expect(final.variantErrors).toEqual([{ nm: '11', error: 'missing card' }])
    expect(final.variants.map((variant) => variant.nm)).toEqual(['10', '12'])
  })

  it('rejects a second concurrent start with a Chinese status message', async () => {
    let resolveQueue
    const controller = Jobs.createJobController({
      now: () => new Date(2026, 6, 14, 15, 30, 9),
      resolveCard: async () => ({
        card: { nm_id: 10, imt_id: 99, imt_name: 'Dress', media: { photo_count: 1 } },
        cardUrl: 'https://basket-01.wbbasket.ru/vol0/part0/10/info/ru/card.json',
        host: 'basket-01.wbbasket.ru'
      }),
      fetchJson: async () => ({ content: [] }),
      probe: async () => false,
      runQueue: async (items) => {
        if (items.length === 1 && items[0].id === 'result') {
          return { items: items.map((item) => ({ ...item, status: 'complete' })), completed: 1, failed: 0, cancelled: 0 }
        }
        return new Promise((resolve) => { resolveQueue = resolve })
      },
      saveState: async () => {},
      emitState: async () => {}
    })

    const running = controller.start({ nm: '10' })
    await waitUntil(() => expect(resolveQueue).toBeTypeOf('function'))
    await expect(controller.start({ nm: '10' })).rejects.toThrow('任务正在进行')
    resolveQueue({ items: [], completed: 0, failed: 0, cancelled: 0 })
    await running
  })

  it('retries only failed media items while keeping the same batch root', async () => {
    const queueCalls = []
    const controller = Jobs.createJobController({
      now: () => new Date(2026, 6, 14, 15, 30, 9),
      resolveCard: async () => ({
        card: { nm_id: 10, imt_id: 99, imt_name: 'Dress', media: { photo_count: 2 } },
        cardUrl: 'https://basket-01.wbbasket.ru/vol0/part0/10/info/ru/card.json',
        host: 'basket-01.wbbasket.ru'
      }),
      fetchJson: async () => ({ content: [] }),
      probe: async () => false,
      runQueue: async (items, options) => {
        queueCalls.push(items.map((item) => item.id))
        if (items.length === 1 && items[0].id === 'result') {
          return { items: items.map((item) => ({ ...item, status: 'complete' })), completed: 1, failed: 0, cancelled: 0 }
        }
        const next = items.map((item, index) => ({ ...item, status: index === 0 ? 'failed' : 'complete', error: index === 0 ? 'bad' : '' }))
        options.onProgress({ total: next.length, completed: 1, failed: 1, cancelled: 0, active: 0, items: next })
        return { items: next, completed: 1, failed: 1, cancelled: 0 }
      },
      saveState: async () => {},
      emitState: async () => {}
    })

    const first = await controller.start({ nm: '10' })
    const retry = await controller.retryFailed()

    expect(queueCalls).toEqual([
      ['10:gallery:1', '10:gallery:2'],
      ['result'],
      ['10:gallery:1']
    ])
    expect(retry.items).toHaveLength(first.items.length)
    expect(retry.items.filter((item) => item.status === 'failed')).toHaveLength(1)
  })

  it('reports retry totals against the full merged batch', async () => {
    const controller = Jobs.createJobController({
      now: () => new Date(2026, 6, 14, 15, 30, 9),
      resolveCard: async () => ({
        card: { nm_id: 10, imt_id: 99, imt_name: 'Dress', media: { photo_count: 3 } },
        cardUrl: 'https://basket-01.wbbasket.ru/vol0/part0/10/info/ru/card.json',
        host: 'basket-01.wbbasket.ru'
      }),
      fetchJson: async () => ({ content: [] }),
      probe: async () => false,
      runQueue: async (items) => {
        if (items.length === 1 && items[0].id === 'result') {
          return { items: items.map((item) => ({ ...item, status: 'complete' })), completed: 1, failed: 0, cancelled: 0 }
        }
        const next = items.map((item, index) => ({
          ...item,
          status: index === 0 ? 'failed' : 'complete',
          error: index === 0 ? 'bad' : ''
        }))
        return { items: next, completed: next.filter((item) => item.status === 'complete').length, failed: 1, cancelled: 0 }
      },
      saveState: async () => {},
      emitState: async () => {}
    })

    const first = await controller.start({ nm: '10' })
    const retry = await controller.retryFailed()

    expect(first.items).toHaveLength(4)
    expect(retry.totalFiles).toBe(4)
    expect(retry.completed).toBeLessThanOrEqual(retry.totalFiles)
  })

  it('downloads result JSON with a fresh signal after stop aborts the media queue', async () => {
    let mediaSignal
    let resultSignal
    let mediaStarted
    const controller = Jobs.createJobController({
      now: () => new Date(2026, 6, 14, 15, 30, 9),
      resolveCard: async () => ({
        card: { nm_id: 10, imt_id: 99, imt_name: 'Dress', media: { photo_count: 2 } },
        cardUrl: 'https://basket-01.wbbasket.ru/vol0/part0/10/info/ru/card.json',
        host: 'basket-01.wbbasket.ru'
      }),
      fetchJson: async () => ({ content: [] }),
      probe: async () => false,
      runQueue: async (items, options) => {
        if (items.length === 1 && items[0].id === 'result') {
          resultSignal = options.signal
          return { items: items.map((item) => ({ ...item, status: 'complete' })), completed: 1, failed: 0, cancelled: 0 }
        }
        mediaSignal = options.signal
        mediaStarted = true
        await new Promise((resolve) => mediaSignal.addEventListener('abort', resolve, { once: true }))
        return {
          items: items.map((item, index) => ({ ...item, status: index === 0 ? 'complete' : 'cancelled' })),
          completed: 1,
          failed: 0,
          cancelled: 1
        }
      },
      saveState: async () => {},
      emitState: async () => {}
    })

    const running = controller.start({ nm: '10' })
    await waitUntil(() => expect(mediaStarted).toBe(true))
    await controller.stop()
    const final = await running

    expect(mediaSignal.aborted).toBe(true)
    expect(resultSignal).toBeTruthy()
    expect(resultSignal.aborted).toBe(false)
    expect(final.items.at(-1).id).toBe('result')
    expect(final.items.at(-1).status).toBe('complete')
    expect(final.phase).toBe('stopped')
  })

  it('reconciles persisted handles and starts only untouched pending files', async () => {
    const started = []
    const saved = {
      phase: 'downloading',
      nm: '10',
      items: [
        { id: 'a', handle: 1, status: 'downloading' },
        { id: 'b', handle: 2, status: 'downloading' },
        { id: 'c', handle: 3, status: 'downloading' },
        { id: 'd', status: 'pending' }
      ]
    }
    const controller = Jobs.createJobController({
      now: () => new Date(0),
      runQueue: async (items) => {
        started.push(...items.map((item) => item.id))
        return { items, completed: 0, failed: 0, cancelled: 0 }
      },
      saveState: async () => {},
      emitState: async () => {}
    })

    const state = await controller.restore(saved, async (handle) => ({
      1: { state: 'complete' },
      2: { state: 'interrupted', error: 'NETWORK_FAILED' },
      3: { state: 'in_progress' }
    })[handle])

    expect(state.items.map((item) => item.status)).toEqual(['complete', 'failed', 'downloading', 'pending'])
    expect(started).toEqual(['d'])
  })

  it('preserves reconciled downloading handles during restored pending progress saves', async () => {
    const savedStates = []
    const saved = {
      phase: 'downloading',
      nm: '10',
      items: [
        { id: 'old', kind: 'gallery', handle: 7, status: 'downloading', filename: 'old.webp' },
        { id: 'new', kind: 'gallery', status: 'pending', filename: 'new.webp' }
      ]
    }
    const controller = Jobs.createJobController({
      now: () => new Date(0),
      runQueue: async (items, options) => {
        const progressItems = items.map((item) => ({ ...item, handle: 8, status: 'downloading' }))
        options.onProgress({
          total: progressItems.length,
          completed: 0,
          failed: 0,
          cancelled: 0,
          active: 1,
          items: progressItems
        })
        return { items: progressItems, completed: 0, failed: 0, cancelled: 0 }
      },
      saveState: async (state) => { savedStates.push(state) },
      emitState: async () => {}
    })

    await controller.restore(saved, async () => ({ state: 'in_progress' }))

    const progressState = savedStates.find((entry) =>
      (entry.items || []).some((item) => item.id === 'new' && item.status === 'downloading'))
    expect(progressState.items.map((item) => ({ id: item.id, handle: item.handle, status: item.status }))).toEqual([
      { id: 'old', handle: 7, status: 'downloading' },
      { id: 'new', handle: 8, status: 'downloading' }
    ])
  })

  it('finalizes a restored job when all media handles have already settled', async () => {
    const queueCalls = []
    const saved = {
      phase: 'downloading',
      nm: '10',
      product: { nm: '10', imtId: '99', title: 'Dress' },
      jobDate: '2026-07-14T07:30:09.000Z',
      variants: [{ nm: '10', label: 'white', gallery: [], rich: [], videos: [] }],
      items: [
        { id: 'a', kind: 'gallery', handle: 1, status: 'downloading', filename: 'media-a.webp' },
        { id: 'b', kind: 'gallery', handle: 2, status: 'downloading', filename: 'media-b.webp' }
      ]
    }
    const controller = Jobs.createJobController({
      now: () => new Date(0),
      runQueue: async (items) => {
        queueCalls.push(items.map((item) => item.id))
        return { items: items.map((item) => ({ ...item, status: 'complete' })), completed: items.length, failed: 0, cancelled: 0 }
      },
      saveState: async () => {},
      emitState: async () => {}
    })

    const state = await controller.restore(saved, async (handle) => ({
      1: { state: 'complete' },
      2: { state: 'interrupted', error: 'NETWORK_FAILED' }
    })[handle])

    expect(queueCalls).toEqual([['result']])
    expect(state.items.map((item) => item.id)).toEqual(['a', 'b', 'result'])
    expect(state.items.at(-1).filename).toMatch(/\.json$/)
    expect(state.phase).toBe('complete')
  })

  it('does not duplicate downloads for restored in-progress handles and finalizes on a later restore', async () => {
    const queueCalls = []
    const saved = {
      phase: 'downloading',
      nm: '10',
      product: { nm: '10', imtId: '99', title: 'Dress' },
      jobDate: '2026-07-14T07:30:09.000Z',
      variants: [{ nm: '10', label: 'white', gallery: [], rich: [], videos: [] }],
      items: [
        { id: 'a', kind: 'gallery', handle: 1, status: 'downloading', filename: 'media-a.webp' }
      ]
    }
    const controller = Jobs.createJobController({
      now: () => new Date(0),
      runQueue: async (items) => {
        queueCalls.push(items.map((item) => item.id))
        return { items: items.map((item) => ({ ...item, status: 'complete' })), completed: items.length, failed: 0, cancelled: 0 }
      },
      saveState: async () => {},
      emitState: async () => {}
    })

    const first = await controller.restore(saved, async () => ({ state: 'in_progress' }))
    const second = await controller.restore(first, async () => ({ state: 'complete' }))

    expect(first.items.map((item) => item.id)).toEqual(['a'])
    expect(first.items[0].status).toBe('downloading')
    expect(queueCalls).toEqual([['result']])
    expect(second.items.map((item) => item.id)).toEqual(['a', 'result'])
    expect(second.phase).toBe('complete')
  })
})
