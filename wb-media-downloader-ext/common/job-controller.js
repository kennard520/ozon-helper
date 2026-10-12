;(function (root, factory) {
  const cardApi = typeof module === 'object' && module.exports
    ? require('./wb-card.js')
    : root.WbMediaCard
  const mediaApi = typeof module === 'object' && module.exports
    ? require('./media-resolver.js')
    : root.WbMediaResolver
  const planApi = typeof module === 'object' && module.exports
    ? require('./download-plan.js')
    : root.WbDownloadPlan
  const queueApi = typeof module === 'object' && module.exports
    ? require('./download-queue.js')
    : root.WbDownloadQueue
  const api = factory(cardApi, mediaApi, planApi, queueApi)
  if (typeof module === 'object' && module.exports) module.exports = api
  root.WbJobController = api
})(typeof globalThis !== 'undefined' ? globalThis : self, function (WbMediaCard, WbMediaResolver, WbDownloadPlan, WbDownloadQueue) {
  const ACTIVE_PHASES = new Set(['scanning', 'resolving', 'downloading'])

  function errorMessage(error) {
    if (!error) return ''
    if (typeof error === 'string') return error
    return error.message || String(error)
  }

  function cloneItem(item) {
    return { ...item }
  }

  function cloneState(state) {
    return {
      ...state,
      items: (state.items || []).map(cloneItem),
      variants: (state.variants || []).map((variant) => ({
        ...variant,
        gallery: [...(variant.gallery || [])],
        rich: [...(variant.rich || [])],
        videos: [...(variant.videos || [])]
      })),
      variantErrors: (state.variantErrors || []).map((item) => ({ ...item }))
    }
  }

  function resultItem(product, variants, items, date) {
    const batchRoot = WbDownloadPlan.buildBatchRoot(product, date)
    const payload = {
      product,
      variants,
      items: items.map(cloneItem),
      generatedAt: date.toISOString()
    }
    return {
      id: 'result',
      nm: String(product.nm || ''),
      kind: 'result',
      url: `data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(payload, null, 2))}`,
      filename: `${batchRoot}/下载结果.json`,
      status: 'pending',
      attempts: 0,
      error: ''
    }
  }

  function normalizeSnapshotItems(currentItems, snapshotItems) {
    if (Array.isArray(snapshotItems)) return snapshotItems.map(cloneItem)
    return (currentItems || []).map(cloneItem)
  }

  function createJobController(deps) {
    const config = deps || {}
    const now = typeof config.now === 'function' ? config.now : () => new Date()
    const saveState = typeof config.saveState === 'function' ? config.saveState : async () => {}
    const emitState = typeof config.emitState === 'function' ? config.emitState : async () => {}
    const resolveCard = typeof config.resolveCard === 'function'
      ? config.resolveCard
      : (nm, cardUrl) => WbMediaCard.resolveCard(nm, cardUrl, config.fetchJson)
    const fetchJson = typeof config.fetchJson === 'function' ? config.fetchJson : async () => ({ content: [] })
    const probe = typeof config.probe === 'function' ? config.probe : async () => false
    const runQueue = typeof config.runQueue === 'function' ? config.runQueue : WbDownloadQueue.runDownloadQueue
    const startDownload = typeof config.start === 'function'
      ? config.start
      : async () => ({ handle: undefined, completion: Promise.resolve() })
    const cancelDownload = typeof config.cancel === 'function' ? config.cancel : async () => {}

    let state = {
      jobId: '',
      nm: '',
      phase: 'idle',
      totalVariants: 0,
      resolvedVariants: 0,
      totalFiles: 0,
      completed: 0,
      failed: 0,
      cancelled: 0,
      currentVariant: '',
      error: '',
      items: [],
      variants: [],
      variantErrors: []
    }
    let active = false
    let abortController = null
    let progressChain = Promise.resolve()

    async function publish(patch) {
      state = cloneState({ ...state, ...(patch || {}) })
      await saveState(cloneState(state))
      await emitState(cloneState(state))
      return cloneState(state)
    }

    function enqueueProgress(patch) {
      progressChain = progressChain.then(() => publish(patch))
      return progressChain
    }

    async function flushProgress() {
      await progressChain
    }

    function queueOptions(signalOverride) {
      return {
        start: startDownload,
        cancel: cancelDownload,
        signal: signalOverride || (abortController && abortController.signal),
        onProgress: (snapshot) => enqueueProgress({
          totalFiles: snapshot.total,
          completed: snapshot.completed,
          failed: snapshot.failed,
          cancelled: snapshot.cancelled,
          items: normalizeSnapshotItems(state.items, snapshot.items)
        }),
        concurrency: config.concurrency,
        retries: config.retries
      }
    }

    function mergedQueueOptions(prefixItems, signalOverride) {
      const prefix = (prefixItems || []).map(cloneItem)
      return {
        ...queueOptions(signalOverride),
        onProgress: (snapshot) => enqueueProgress({
          totalFiles: prefix.length + snapshot.total,
          completed: prefix.filter((item) => item.status === 'complete').length + snapshot.completed,
          failed: prefix.filter((item) => item.status === 'failed').length + snapshot.failed,
          cancelled: prefix.filter((item) => item.status === 'cancelled').length + snapshot.cancelled,
          items: [...prefix, ...normalizeSnapshotItems([], snapshot.items)]
        })
      }
    }

    function restoredPendingQueueOptions(fullItems, pendingItems) {
      const baseItems = (fullItems || []).map(cloneItem)
      const pendingBase = (pendingItems || []).map(cloneItem)
      return {
        ...queueOptions(),
        onProgress: (snapshot) => {
          const byId = new Map(normalizeSnapshotItems(pendingBase, snapshot.items)
            .map((item) => [item.id, item]))
          const merged = baseItems.map((item) => byId.get(item.id) || item)
          return enqueueProgress({
            totalFiles: merged.length,
            completed: merged.filter((item) => item.status === 'complete').length,
            failed: merged.filter((item) => item.status === 'failed').length,
            cancelled: merged.filter((item) => item.status === 'cancelled').length,
            items: merged
          })
        }
      }
    }

    async function resolveVariant(nm, hintUrl, observedUrls, index, knownResolved, options) {
      const opts = options || {}
      const resolved = knownResolved || await resolveCard(nm, hintUrl)
      const card = resolved.card || {}
      const gallery = WbMediaResolver.galleryUrls(card, resolved.cardUrl, nm)
      const videos = []
      if (card && card.media && card.media.has_video === true) {
        const video = await WbMediaResolver.resolveVideo(
          WbMediaResolver.videoCandidates(card, nm, observedUrls),
          probe
        )
        if (video) videos.push(video)
      }
      return {
        nm: String(nm),
        label: WbMediaCard.variantLabel(card, index),
        gallery,
        rich: [],
        videos,
        cardUrl: resolved.cardUrl
      }
    }

    async function runItems(items, nextPhase) {
      await publish({
        phase: nextPhase || 'downloading',
        totalFiles: items.length,
        completed: items.filter((item) => item.status === 'complete').length,
        failed: items.filter((item) => item.status === 'failed').length,
        cancelled: items.filter((item) => item.status === 'cancelled').length,
        items
      })
      const result = await runQueue(items, queueOptions())
      await flushProgress()
      const resultItems = normalizeSnapshotItems(items, result && result.items)
      return publish({
        items: resultItems,
        completed: result ? result.completed : resultItems.filter((item) => item.status === 'complete').length,
        failed: result ? result.failed : resultItems.filter((item) => item.status === 'failed').length,
        cancelled: result ? result.cancelled : resultItems.filter((item) => item.status === 'cancelled').length
      })
    }

    function restoredProduct(saved) {
      const product = saved.product || {}
      return {
        nm: String(product.nm || saved.nm || state.nm || ''),
        imtId: String(product.imtId || product.imt_id || saved.imtId || saved.nm || state.nm || ''),
        title: String(product.title || saved.title || saved.nm || state.nm || 'WB')
      }
    }

    function restoredJobDate(saved) {
      const explicit = new Date(saved.jobDate || saved.startedAt || '')
      if (!Number.isNaN(explicit.getTime())) return explicit
      const match = String(saved.jobId || '').match(/-(\d+)$/)
      const fromJobId = match ? new Date(Number(match[1])) : null
      if (fromJobId && !Number.isNaN(fromJobId.getTime())) return fromJobId
      return now()
    }

    async function runResultItem(mediaItems, product, variants, jobDate, options) {
      const resultOptions = options || {}
      const resultDownload = resultItem(product, variants, mediaItems, jobDate)
      await publish({
        phase: 'downloading',
        totalFiles: mediaItems.length + 1,
        completed: mediaItems.filter((item) => item.status === 'complete').length,
        failed: mediaItems.filter((item) => item.status === 'failed').length,
        cancelled: mediaItems.filter((item) => item.status === 'cancelled').length,
        items: [...mediaItems, resultDownload]
      })
      const result = await runQueue([resultDownload], mergedQueueOptions(mediaItems, resultOptions.signal))
      await flushProgress()
      const [finalResultItem] = normalizeSnapshotItems([resultDownload], result && result.items)
      const finalItems = [...mediaItems, finalResultItem || resultDownload]
      return publish({
        items: finalItems,
        completed: finalItems.filter((item) => item.status === 'complete').length,
        failed: finalItems.filter((item) => item.status === 'failed').length,
        cancelled: finalItems.filter((item) => item.status === 'cancelled').length,
        totalFiles: finalItems.length
      })
    }

    async function start(payload) {
      if (active) throw new Error('任务正在进行')
      active = true
      abortController = new AbortController()
      const input = payload || {}
      const nm = String(input.nm || '').trim()
      const resourceUrls = Array.isArray(input.resourceUrls) ? input.resourceUrls : []
      const onlyMain = Boolean(input.onlyMain)
      const jobDate = now()
      try {
        await publish({
          jobId: `${nm}-${jobDate.getTime()}`,
          nm,
          phase: 'scanning',
          totalVariants: 0,
          resolvedVariants: 0,
          totalFiles: 0,
          completed: 0,
          failed: 0,
          cancelled: 0,
          currentVariant: '',
          error: '',
          items: [],
          variants: [],
          variantErrors: []
        })

        const current = await resolveCard(nm, input.cardUrl || '')
        const variantIds = onlyMain
          ? [nm]
          : [nm, ...WbMediaCard.variantIds(current.card, nm).filter((id) => id !== nm)]
        await publish({ phase: 'resolving', totalVariants: variantIds.length })

        const variants = []
        const variantErrors = []
        for (let index = 0; index < variantIds.length; index++) {
          const variantNm = variantIds[index]
          await publish({ currentVariant: variantNm })
          try {
            const variant = await resolveVariant(
              variantNm,
              variantNm === nm ? current.cardUrl : '',
              resourceUrls,
              index,
              variantNm === nm ? current : null,
              { onlyMain }
            )
            variants.push(variant)
            await publish({ resolvedVariants: variants.length, variants })
          } catch (error) {
            variantErrors.push({ nm: variantNm, error: errorMessage(error) })
            await publish({ variantErrors })
          }
        }

        const product = {
          nm,
          imtId: String(current.card && (current.card.imt_id || current.card.imtId || nm)),
          title: String(current.card && (current.card.imt_name || current.card.subject_name || current.card.name || nm))
        }
        await publish({ product, jobDate: jobDate.toISOString() })
        const mediaItems = WbDownloadPlan.buildDownloadPlan(product, variants, jobDate)
        const mediaQueueState = await runItems(mediaItems, 'downloading')
        const mediaFinalItems = normalizeSnapshotItems(mediaItems, mediaQueueState.items)
        const resultAbortController = new AbortController()
        const queueState = await runResultItem(mediaFinalItems, product, variants, jobDate, {
          signal: resultAbortController.signal
        })
        const stopped = abortController.signal.aborted || (queueState.items || []).some((item) => item.status === 'cancelled')
        await flushProgress()
        return publish({ phase: stopped ? 'stopped' : 'complete', currentVariant: '' })
      } catch (error) {
        await publish({ phase: abortController.signal.aborted ? 'stopped' : 'error', error: errorMessage(error) })
        throw error
      } finally {
        active = false
        abortController = null
      }
    }

    async function stop() {
      if (abortController) abortController.abort()
      return publish({ phase: 'stopped' })
    }

    async function retryFailed() {
      if (active) throw new Error('任务正在进行')
      const failedItems = (state.items || [])
        .filter((item) => item.status === 'failed' && item.kind !== 'result')
        .map((item) => ({ ...item, status: 'pending', attempts: 0, error: '', handle: undefined }))
      if (!failedItems.length) return cloneState(state)

      active = true
      abortController = new AbortController()
      try {
        const before = state.items || []
        await runItems(failedItems, 'downloading')
        const byId = new Map((state.items || []).map((item) => [item.id, item]))
        const merged = before.map((item) => byId.get(item.id) || item)
        return publish({
          phase: abortController.signal.aborted ? 'stopped' : 'complete',
          items: merged,
          completed: merged.filter((item) => item.status === 'complete').length,
          failed: merged.filter((item) => item.status === 'failed').length,
          cancelled: merged.filter((item) => item.status === 'cancelled').length,
          totalFiles: merged.length
        })
      } finally {
        active = false
        abortController = null
      }
    }

    async function finalizeRestoredIfSettled(saved) {
      const items = state.items || []
      const mediaItems = items.filter((item) => item.kind !== 'result')
      const resultItems = items.filter((item) => item.kind === 'result')
      const hasOpenMedia = mediaItems.some((item) => item.status === 'pending' || item.status === 'downloading')
      const hasOpenResult = resultItems.some((item) => item.status === 'pending' || item.status === 'downloading')
      if (hasOpenMedia || hasOpenResult) return cloneState(state)

      let queueState = cloneState(state)
      if (!resultItems.length) {
        const resultAbortController = new AbortController()
        queueState = await runResultItem(
          mediaItems.map(cloneItem),
          restoredProduct(saved),
          saved.variants || state.variants || [],
          restoredJobDate(saved),
          { signal: resultAbortController.signal }
        )
      }

      const finalItems = queueState.items || state.items || []
      const stopped = finalItems.some((item) => item.status === 'cancelled')
      await flushProgress()
      return publish({ phase: stopped ? 'stopped' : 'complete', currentVariant: '' })
    }

    async function restore(savedState, reconcileDownload) {
      if (active) return cloneState(state)
      active = true
      const saved = cloneState(savedState || {})
      try {
        const items = (saved.items || []).map(cloneItem)
        for (const item of items) {
          if (!item.handle) continue
          const chromeState = await reconcileDownload(item.handle)
          if (!chromeState) continue
          if (chromeState.state === 'complete') {
            item.status = 'complete'
            item.error = ''
          } else if (chromeState.state === 'interrupted') {
            item.status = 'failed'
            item.error = chromeState.error || item.error || 'interrupted'
          } else if (chromeState.state === 'in_progress') {
            item.status = 'downloading'
          }
        }

        state = cloneState({
          ...state,
          ...saved,
          items,
          completed: items.filter((item) => item.status === 'complete').length,
          failed: items.filter((item) => item.status === 'failed').length,
          cancelled: items.filter((item) => item.status === 'cancelled').length
        })
        await publish({})

        const pending = items.filter((item) => item.status === 'pending').map(cloneItem)
        if (ACTIVE_PHASES.has(state.phase) && pending.length) {
          abortController = new AbortController()
          const result = await runQueue(pending, restoredPendingQueueOptions(items, pending))
          await flushProgress()
          const byId = new Map(normalizeSnapshotItems(pending, result && result.items).map((item) => [item.id, item]))
          const merged = items.map((item) => byId.get(item.id) || item)
          await publish({
            items: merged,
            completed: merged.filter((item) => item.status === 'complete').length,
            failed: merged.filter((item) => item.status === 'failed').length,
            cancelled: merged.filter((item) => item.status === 'cancelled').length,
            totalFiles: merged.length
          })
          abortController = null
        }
        if (ACTIVE_PHASES.has(state.phase)) {
          await finalizeRestoredIfSettled(saved)
        }
        return cloneState(state)
      } finally {
        active = false
      }
    }

    function getState() {
      return cloneState(state)
    }

    function isActive() {
      return active
    }

    return { start, stop, retryFailed, getState, restore, isActive }
  }

  return { createJobController }
})
