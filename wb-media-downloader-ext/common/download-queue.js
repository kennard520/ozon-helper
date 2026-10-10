;(function (root, factory) {
  const api = factory()
  if (typeof module === 'object' && module.exports) module.exports = api
  root.WbDownloadQueue = api
})(typeof globalThis !== 'undefined' ? globalThis : self, function () {
  const DEFAULT_CONCURRENCY = 3
  const DEFAULT_RETRIES = 2

  function errorMessage(error) {
    if (!error) return ''
    if (typeof error === 'string') return error
    return error.message || String(error)
  }

  function cloneItem(item) {
    return { ...item }
  }

  function cloneSnapshot(items) {
    const completed = items.filter((item) => item.status === 'complete').length
    const failed = items.filter((item) => item.status === 'failed').length
    const cancelled = items.filter((item) => item.status === 'cancelled').length
    const active = items.filter((item) => item.status === 'downloading').length
    return {
      total: items.length,
      completed,
      failed,
      cancelled,
      active,
      items: items.map(cloneItem)
    }
  }

  function finalResult(items) {
    const snapshot = cloneSnapshot(items)
    return {
      items: snapshot.items,
      completed: snapshot.completed,
      failed: snapshot.failed,
      cancelled: snapshot.cancelled
    }
  }

  function normalizePositiveInteger(value, fallback) {
    const number = Number(value)
    if (!Number.isFinite(number) || number < 1) return fallback
    return Math.floor(number)
  }

  function normalizeNonNegativeInteger(value, fallback) {
    const number = Number(value)
    if (!Number.isFinite(number) || number < 0) return fallback
    return Math.floor(number)
  }

  async function runDownloadQueue(sourceItems, options) {
    const config = options || {}
    if (typeof config.start !== 'function') throw new TypeError('options.start is required')

    const items = (sourceItems || []).map((item) => ({
      ...item,
      status: item.status || 'pending',
      attempts: item.attempts || 0,
      error: item.error || ''
    }))
    const concurrency = Math.min(
      normalizePositiveInteger(config.concurrency, DEFAULT_CONCURRENCY),
      items.length || 1
    )
    const maxAttempts = normalizeNonNegativeInteger(config.retries, DEFAULT_RETRIES) + 1
    const onProgress = typeof config.onProgress === 'function' ? config.onProgress : () => {}
    const cancel = typeof config.cancel === 'function' ? config.cancel : async () => {}
    const signal = config.signal
    const active = new Map()
    let nextIndex = 0
    let aborted = Boolean(signal && signal.aborted)

    function progress() {
      onProgress(cloneSnapshot(items))
    }

    async function cancelOneDownload(handle, item) {
      if (item.cancelRequested) return
      item.cancelRequested = true
      try {
        await cancel(handle)
      } catch (error) {
        item.error = errorMessage(error)
      }
    }

    async function cancelActiveDownloads() {
      await Promise.all([...active.values()].map(async ({ handle, item }) => {
        await cancelOneDownload(handle, item)
      }))
    }

    function cancelUntouchedPending() {
      for (const item of items) {
        if (item.status === 'pending') {
          item.status = 'cancelled'
          item.error = ''
        }
      }
    }

    async function abortQueue() {
      if (aborted) return
      aborted = true
      cancelUntouchedPending()
      progress()
      await cancelActiveDownloads()
    }

    let abortListener
    if (signal && typeof signal.addEventListener === 'function') {
      abortListener = () => {
        abortQueue()
      }
      signal.addEventListener('abort', abortListener, { once: true })
    }

    if (aborted) {
      try {
        cancelUntouchedPending()
        progress()
        return finalResult(items)
      } finally {
        if (signal && abortListener && typeof signal.removeEventListener === 'function') {
          signal.removeEventListener('abort', abortListener)
        }
      }
    }

    async function runAttempt(item) {
      const activeKey = {}
      item.attempts += 1
      item.error = ''

      let started
      try {
        started = await config.start(item, { signal })
        item.handle = started && started.handle
        active.set(activeKey, { item, handle: item.handle })
        if (aborted || item.cancelRequested || item.status === 'cancelled') {
          item.status = 'cancelled'
          await cancelOneDownload(item.handle, item)
          await started.completion
          progress()
          return true
        }
        item.status = 'downloading'
        progress()
        await started.completion
        if (aborted || item.cancelRequested) {
          item.status = 'cancelled'
        } else {
          item.status = 'complete'
        }
        progress()
        return true
      } catch (error) {
        if (aborted || item.cancelRequested) {
          item.status = 'cancelled'
          item.error = errorMessage(error)
          progress()
          return true
        }
        item.error = errorMessage(error)
        if (item.attempts >= maxAttempts) {
          item.status = 'failed'
          progress()
          return true
        }
        item.status = 'pending'
        progress()
        return false
      } finally {
        active.delete(activeKey)
      }
    }

    async function worker() {
      while (!aborted) {
        const index = nextIndex
        nextIndex += 1
        const item = items[index]
        if (!item) return
        if (item.status !== 'pending') continue

        let finished = false
        while (!finished && !aborted) {
          finished = await runAttempt(item)
        }
      }
    }

    try {
      const workers = Array.from({ length: concurrency }, () => worker())
      await Promise.all(workers)
      if (aborted) {
        cancelUntouchedPending()
        await cancelActiveDownloads()
        for (const item of items) {
          if (item.status === 'downloading') item.status = 'cancelled'
        }
        progress()
      }
      return finalResult(items)
    } finally {
      if (signal && abortListener && typeof signal.removeEventListener === 'function') {
        signal.removeEventListener('abort', abortListener)
      }
    }
  }

  return { runDownloadQueue }
})
