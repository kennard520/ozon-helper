import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import Settings from '../src/views/Settings.vue'
import AiImageDialog from '../src/components/AiImageDialog.vue'
import AiVideoDialog from '../src/components/AiVideoDialog.vue'
import { api } from '../src/api.js'

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => vi.restoreAllMocks())

describe('Settings.vue 图片/视频 AI 区块', () => {
  it('保存带 ai_image/ai_video；key 只在非空时发送并在保存后清空', async () => {
    const spy = vi.spyOn(api, 'saveSettings').mockResolvedValue({ settings: {}, status: {}, paths: {} })
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    w.vm.aiImage.engine = 'agnes'
    w.vm.aiImage.api_key = 'sk-img'
    w.vm.aiImage.model = 'agnes-image-2.1-flash'
    w.vm.aiVideo.api_key = 'sk-vid'
    await w.vm.save()
    const payload = spy.mock.calls[0][0]
    expect(payload.ai_image).toMatchObject({ engine: 'agnes', api_key: 'sk-img', model: 'agnes-image-2.1-flash' })
    expect(payload.ai_video).toMatchObject({ engine: 'agnes', api_key: 'sk-vid' })
    expect(w.vm.aiImage.api_key).toBe('')   // 密钥惯例：保存后清空输入框
    expect(w.vm.aiVideo.api_key).toBe('')
  })

  it('key 为空时不发送 api_key（不覆盖已存值）', async () => {
    const spy = vi.spyOn(api, 'saveSettings').mockResolvedValue({ settings: {} })
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    await w.vm.save()
    const payload = spy.mock.calls[0][0]
    expect('api_key' in payload.ai_image).toBe(false)
    expect('api_key' in payload.ai_video).toBe(false)
  })

  it('settings 到达后回填 ai_image/ai_video 字段（key 除外）', async () => {
    const { useAppStore } = await import('../src/stores/app.js')
    const store = useAppStore()
    store.settings = {}
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    store.settings = {
      ai_image: { engine: 'agnes', api_base: 'https://apihub.agnes-ai.com', model: 'agnes-image-2.1-flash', api_key_saved: true },
      ai_video: { engine: 'agnes', api_base: '', model: 'agnes-video-v2.0', api_key_saved: true },
    }
    await w.vm.$nextTick()
    expect(w.vm.aiImage.engine).toBe('agnes')
    expect(w.vm.aiImage.api_base).toBe('https://apihub.agnes-ai.com')
    expect(w.vm.aiImage.model).toBe('agnes-image-2.1-flash')
    expect(w.vm.aiImage.api_key).toBe('')   // key 永不回填
    expect(w.vm.aiVideo.model).toBe('agnes-video-v2.0')
  })
})

const IMAGES = [
  { url: 'https://a/1.jpg', disp: '/media/draft-1/01.jpg' },
  { url: 'https://a/2.jpg', disp: 'https://a/2.jpg' },
]

describe('AiImageDialog.vue', () => {
  it('img2img：默认选第一张源图，generate 发 mode/prompt/source_url/as_main', async () => {
    const spy = vi.spyOn(api, 'aiImage').mockResolvedValue({ ok: true, draft: { id: 1 } })
    const w = mount(AiImageDialog, {
      props: { modelValue: true, draftId: 1, images: IMAGES },
      global: { plugins: [ElementPlus] },
    })
    expect(w.vm.mode).toBe('img2img')
    expect(w.vm.sourceUrl).toBe('https://a/1.jpg')
    w.vm.usePreset(w.vm.presets[0])   // 白底主图：img2img + as_main
    await w.vm.generate()
    const [id, p] = spy.mock.calls[0]
    expect(id).toBe(1)
    expect(p.mode).toBe('img2img')
    expect(p.source_url).toBe('https://a/1.jpg')
    expect(p.as_main).toBe(true)
    expect(p.prompt).toContain('white')
    expect(w.emitted('done')[0][0]).toEqual({ id: 1 })
    expect(w.emitted('update:modelValue').at(-1)[0]).toBe(false)
  })

  it('text2img：不带 source_url；空提示词不发请求', async () => {
    const spy = vi.spyOn(api, 'aiImage').mockResolvedValue({ ok: true, draft: { id: 2 } })
    const w = mount(AiImageDialog, {
      props: { modelValue: true, draftId: 2, images: [] },
      global: { plugins: [ElementPlus] },
    })
    expect(w.vm.mode).toBe('text2img')   // 无图自动退文生图
    await w.vm.generate()                 // 空提示词 → 拦截
    expect(spy).not.toHaveBeenCalled()
    w.vm.prompt = 'banner'
    await w.vm.generate()
    expect(spy.mock.calls[0][1].source_url).toBeUndefined()
  })
})

describe('AiVideoDialog.vue', () => {
  it('start 调 api.aiVideo 并轮询到 done 后 emit done', async () => {
    vi.useFakeTimers()
    try {
      vi.spyOn(api, 'aiVideoStatus').mockResolvedValueOnce({ status: 'idle' })  // 打开时查一次
      const w = mount(AiVideoDialog, {
        props: { modelValue: true, draftId: 5, images: IMAGES },
        global: { plugins: [ElementPlus] },
      })
      await flushPromises()
      expect(w.vm.imageUrl).toBe('https://a/1.jpg')
      vi.spyOn(api, 'aiVideo').mockResolvedValue({ status: 'running', draft_id: 5, progress: 0 })
      vi.spyOn(api, 'aiVideoStatus')
        .mockResolvedValueOnce({ status: 'running', draft_id: 5, progress: 60 })
        .mockResolvedValueOnce({ status: 'done', draft_id: 5, progress: 100, url: 'https://g/v.mp4' })
      await w.vm.start()
      expect(api.aiVideo).toHaveBeenCalledWith(5, expect.objectContaining({ image_url: 'https://a/1.jpg' }))
      expect(w.vm.job.status).toBe('running')
      await vi.advanceTimersByTimeAsync(3000)
      expect(w.vm.job.progress).toBe(60)
      await vi.advanceTimersByTimeAsync(3000)
      expect(w.vm.job.status).toBe('done')
      expect(w.emitted('done')).toBeTruthy()
    } finally {
      vi.useRealTimers()
    }
  })

  it('已有别的草稿任务在跑时提示并不轮询自己', async () => {
    vi.spyOn(api, 'aiVideoStatus').mockResolvedValue({ status: 'idle' })
    const w = mount(AiVideoDialog, {
      props: { modelValue: true, draftId: 5, images: IMAGES },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    vi.spyOn(api, 'aiVideo').mockResolvedValue({ status: 'running', draft_id: 99, progress: 10 })
    await w.vm.start()
    expect(w.vm.job.draft_id).toBe(99)
    expect(w.emitted('done')).toBeFalsy()
  })
})
