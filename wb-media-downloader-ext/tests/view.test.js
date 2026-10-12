// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { runInNewContext } from 'node:vm'

function loadView() {
  const context = { document, console, globalThis: {} }
  context.window = context
  context.self = context
  runInNewContext(fs.readFileSync(path.join(process.cwd(), 'content/view.js'), 'utf8'), context)
  return context.WbMediaView || context.globalThis.WbMediaView
}

describe('WB media downloader floating panel', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('renders idle, running, and completed actions without page text leakage', () => {
    const View = loadView()
    const handlers = { startMain: vi.fn(), startAll: vi.fn(), stop: vi.fn(), retry: vi.fn(), open: vi.fn() }
    const panel = View.createPanel(document, handlers)

    panel.render({ phase: 'idle' })
    expect(panel.root.id).toBe('wb-media-downloader')
    expect(panel.root.textContent).toContain('下载主图和视频')
    expect(panel.root.textContent).toContain('下载全部变体')

    panel.render({
      phase: 'downloading',
      resolvedVariants: 2,
      totalVariants: 5,
      completed: 27,
      totalFiles: 46,
      failed: 1,
      currentVariant: '<img src=x onerror=alert(1)>蓝色'
    })
    expect(panel.root.textContent).toContain('27 / 46')
    expect(panel.root.textContent).toContain('停止任务')
    expect(panel.root.innerHTML).not.toContain('<img src=x')

    panel.render({ phase: 'complete', completed: 44, totalFiles: 46, failed: 2 })
    expect(panel.root.textContent).toContain('重试失败项')
    expect(panel.root.textContent).toContain('打开下载目录')
  })

  it('wires action buttons to injected handlers and destroy removes the root', () => {
    const View = loadView()
    const handlers = { startMain: vi.fn(), startAll: vi.fn(), stop: vi.fn(), retry: vi.fn(), open: vi.fn() }
    const panel = View.createPanel(document, handlers)

    panel.render({ phase: 'idle' })
    panel.root.querySelector('[data-action="startMain"]').click()
    expect(handlers.startMain).toHaveBeenCalledTimes(1)
    panel.root.querySelector('[data-action="startAll"]').click()
    expect(handlers.startAll).toHaveBeenCalledTimes(1)

    panel.render({ phase: 'downloading' })
    panel.root.querySelector('[data-action="stop"]').click()
    expect(handlers.stop).toHaveBeenCalledTimes(1)

    panel.render({ phase: 'complete', failed: 1 })
    panel.root.querySelector('[data-action="retry"]').click()
    panel.root.querySelector('[data-action="open"]').click()
    expect(handlers.retry).toHaveBeenCalledTimes(1)
    expect(handlers.open).toHaveBeenCalledTimes(1)

    panel.destroy()
    expect(document.getElementById('wb-media-downloader')).toBeNull()
  })
})
