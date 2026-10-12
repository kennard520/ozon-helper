;(function (root, factory) {
  const api = factory()
  if (typeof module === 'object' && module.exports) module.exports = api
  root.WbMediaView = api
})(typeof globalThis !== 'undefined' ? globalThis : self, function () {
  const LABELS = {
    title: 'WB 素材下载',
    startMain: '下载主图和视频',
    startAll: '下载全部变体',
    stop: '停止任务',
    retry: '重试失败项',
    open: '打开下载目录',
    newRun: '重新下载',
    idle: '选择下载模式',
    scanning: '正在扫描变体素材',
    resolving: '正在解析素材链接',
    downloading: '正在下载素材',
    complete: '下载完成',
    stopped: '任务已停止',
    error: '任务出错'
  }

  function number(value) {
    const parsed = Number(value)
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0
  }

  function text(doc, tag, className, value) {
    const node = doc.createElement(tag)
    if (className) node.className = className
    node.textContent = value
    return node
  }

  function button(doc, action, label, primary) {
    const node = doc.createElement('button')
    node.type = 'button'
    node.dataset.action = action
    node.className = primary ? 'wb-md-btn wb-md-btn-primary' : 'wb-md-btn'
    node.textContent = label
    return node
  }

  function statusFor(state) {
    const phase = (state && state.phase) || 'idle'
    if (phase === 'scanning' || phase === 'resolving') {
      return `${LABELS[phase]}：${number(state.resolvedVariants)} / ${number(state.totalVariants)}`
    }
    if (phase === 'downloading') return LABELS.downloading
    if (phase === 'complete') return LABELS.complete
    if (phase === 'stopped') return LABELS.stopped
    if (phase === 'error') return LABELS.error
    return LABELS.idle
  }

  function detailFor(state) {
    const phase = (state && state.phase) || 'idle'
    if (phase === 'downloading') {
      const parts = [`${number(state.completed)} / ${number(state.totalFiles)}`]
      if (number(state.failed) > 0) parts.push(`失败 ${number(state.failed)}`)
      if (state.currentVariant) parts.push(`当前：${String(state.currentVariant)}`)
      return parts.join(' · ')
    }
    if (phase === 'complete' || phase === 'stopped') {
      const parts = [`完成 ${number(state.completed)} / ${number(state.totalFiles)}`]
      if (number(state.failed) > 0) parts.push(`失败 ${number(state.failed)}`)
      return parts.join(' · ')
    }
    if (phase === 'error') return String((state && state.error) || '未知错误')
    return ''
  }

  function progressValue(state) {
    const total = number(state && state.totalFiles)
    if (!total) return 0
    return Math.min(total, number(state && state.completed)) / total
  }

  function actionsFor(doc, state) {
    const phase = (state && state.phase) || 'idle'
    if (phase === 'scanning' || phase === 'resolving' || phase === 'downloading') {
      return [button(doc, 'stop', LABELS.stop, false)]
    }
    if (phase === 'complete' || phase === 'stopped') {
      const actions = []
      if (number(state.failed) > 0) actions.push(button(doc, 'retry', LABELS.retry, false))
      actions.push(button(doc, 'open', LABELS.open, false))
      actions.push(button(doc, 'startMain', LABELS.startMain, true))
      actions.push(button(doc, 'startAll', LABELS.startAll, false))
      return actions
    }
    if (phase === 'error') return [button(doc, 'startMain', LABELS.startMain, true)]
    return [button(doc, 'startMain', LABELS.startMain, true), button(doc, 'startAll', LABELS.startAll, false)]
  }

  function createPanel(doc, handlers) {
    const root = doc.createElement('section')
    root.id = 'wb-media-downloader'
    root.setAttribute('aria-live', 'polite')

    const safeHandlers = handlers || {}
    const onClick = (event) => {
      const action = event.target && event.target.dataset && event.target.dataset.action
      if (action && typeof safeHandlers[action] === 'function') safeHandlers[action]()
    }
    root.addEventListener('click', onClick)
    ;(doc.body || doc.documentElement).appendChild(root)

    function render(state) {
      const snapshot = state || { phase: 'idle' }
      const header = text(doc, 'div', 'wb-md-title', LABELS.title)
      const status = text(doc, 'div', 'wb-md-status', statusFor(snapshot))
      const detail = text(doc, 'div', 'wb-md-detail', detailFor(snapshot))
      const progress = doc.createElement('progress')
      progress.className = 'wb-md-progress'
      progress.max = 1
      progress.value = progressValue(snapshot)
      const actions = doc.createElement('div')
      actions.className = 'wb-md-actions'
      actionsFor(doc, snapshot).forEach((node) => actions.appendChild(node))
      root.replaceChildren(header, status, detail, progress, actions)
    }

    function destroy() {
      root.removeEventListener('click', onClick)
      root.remove()
    }

    render({ phase: 'idle' })
    return { root, render, destroy }
  }

  return { createPanel }
})
