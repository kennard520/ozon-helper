import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { describe, expect, it } from 'vitest'
import Queue from '../common/download-queue.js'

describe('download queue', () => {
  it('never exceeds three active downloads and retries twice', async () => {
    let active = 0
    let peak = 0
    const attempts = new Map()
    const items = Array.from({ length: 5 }, (_, index) => ({
      id: String(index),
      status: 'pending',
      attempts: 0
    }))

    const result = await Queue.runDownloadQueue(items, {
      concurrency: 3,
      retries: 2,
      start: async (item) => {
        active++
        peak = Math.max(peak, active)
        const count = (attempts.get(item.id) || 0) + 1
        attempts.set(item.id, count)
        return {
          handle: `download-${item.id}-${count}`,
          completion: Promise.resolve().then(() => {
            active--
            if (item.id === '0' && count < 3) throw new Error('temporary')
          })
        }
      },
      cancel: async () => {},
      onProgress: () => {}
    })

    expect(peak).toBeLessThanOrEqual(3)
    expect(attempts.get('0')).toBe(3)
    expect(result.completed).toBe(5)
    expect(result.failed).toBe(0)
    expect(result.cancelled).toBe(0)
    expect(result.items.every((item) => item.status === 'complete')).toBe(true)
  })

  it('aborts active downloads, leaves complete items complete, and cancels untouched pending items', async () => {
    const controller = new AbortController()
    const cancelCalls = []
    const completions = new Map()
    const items = Array.from({ length: 5 }, (_, index) => ({
      id: String(index),
      status: 'pending',
      attempts: 0
    }))

    const result = await Queue.runDownloadQueue(items, {
      concurrency: 1,
      retries: 2,
      signal: controller.signal,
      start: async (item) => {
        if (item.id === '0') {
          return {
            handle: `download-${item.id}`,
            completion: Promise.resolve()
          }
        }
        return {
          handle: `download-${item.id}`,
          completion: new Promise((resolve) => {
            completions.set(item.id, resolve)
          })
        }
      },
      cancel: async (handle) => {
        cancelCalls.push(handle)
        const id = String(handle).replace('download-', '')
        completions.get(id)?.()
      },
      onProgress: (snapshot) => {
        if (snapshot.active > 0 && snapshot.completed > 0 && !controller.signal.aborted) {
          snapshot.items[0].status = 'mutated snapshot must not leak'
          controller.abort()
        }
      }
    })

    expect(cancelCalls).toContain('download-1')
    expect(result.items[0].status).toBe('complete')
    expect(result.items.some((item) => item.status === 'cancelled' && item.attempts === 0)).toBe(true)
    expect(result.cancelled).toBeGreaterThanOrEqual(1)
    expect(result.completed).toBe(1)
  })

  it('cancels a handle that appears after abort while start is still pending', async () => {
    const controller = new AbortController()
    let resolveStart
    let resolveCompletion
    const cancelCalls = []
    const queuePromise = Queue.runDownloadQueue([
      { id: 'slow-start', status: 'pending', attempts: 0 }
    ], {
      signal: controller.signal,
      start: async () => new Promise((resolve) => {
        resolveStart = resolve
      }),
      cancel: async (handle) => {
        cancelCalls.push(handle)
        resolveCompletion()
      }
    })

    controller.abort()
    resolveStart({
      handle: 'late-handle',
      completion: new Promise((resolve) => {
        resolveCompletion = resolve
      })
    })

    const result = await Promise.race([
      queuePromise,
      new Promise((resolve) => setTimeout(() => resolve('timed out'), 50))
    ])

    expect(result).not.toBe('timed out')
    expect(cancelCalls).toEqual(['late-handle'])
    expect(result.items[0].status).toBe('cancelled')
  })

  it('cancels every active handle even when queue items have duplicate ids', async () => {
    const controller = new AbortController()
    const completionResolvers = new Map()
    const cancelCalls = []
    const queuePromise = Queue.runDownloadQueue([
      { id: 'duplicate', status: 'pending', attempts: 0 },
      { id: 'duplicate', status: 'pending', attempts: 0 }
    ], {
      concurrency: 2,
      signal: controller.signal,
      start: async () => {
        const handle = `handle-${completionResolvers.size}`
        return {
          handle,
          completion: new Promise((resolve) => {
            completionResolvers.set(handle, resolve)
          })
        }
      },
      cancel: async (handle) => {
        cancelCalls.push(handle)
        completionResolvers.get(handle)?.()
      },
      onProgress: (snapshot) => {
        if (snapshot.active === 2 && !controller.signal.aborted) controller.abort()
      }
    })

    const result = await Promise.race([
      queuePromise,
      new Promise((resolve) => setTimeout(() => resolve('timed out'), 50))
    ])

    expect(result).not.toBe('timed out')
    expect(cancelCalls.sort()).toEqual(['handle-0', 'handle-1'])
    expect(result.items.every((item) => item.status === 'cancelled')).toBe(true)
  })

  it('marks exhausted failures with a useful message and attempt count', async () => {
    const [item] = await Queue.runDownloadQueue([
      { id: 'bad', status: 'pending', attempts: 0 }
    ], {
      retries: 2,
      start: async (queueItem) => ({
        handle: `download-${queueItem.id}-${queueItem.attempts}`,
        completion: Promise.reject(new Error('network broke'))
      })
    }).then((result) => result.items)

    expect(item.status).toBe('failed')
    expect(item.attempts).toBe(3)
    expect(item.error).toContain('network broke')
  })

  it('loads browser UMD global style', () => {
    const context = {}
    runInNewContext(readFileSync(new URL('../common/download-queue.js', import.meta.url), 'utf8'), context)

    expect(typeof context.WbDownloadQueue.runDownloadQueue).toBe('function')
  })
})
