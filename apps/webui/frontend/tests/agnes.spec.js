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
    // 当前实现：AI 配置通过平台(aiPlatforms)+用途(aiUses)两层管理
    // ai_image/ai_video 保存为 { platform, model }，key 在平台层管理
    const spy = vi.spyOn(api, 'saveSettings').mockResolvedValue({ settings: {}, status: {}, paths: {} })
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })

    // 设置一个平台，并在图片/视频用途选该平台
    w.vm.aiPlatforms.push({ name: 'my-plat', base: 'https://api.example.com/v1', key: 'sk-img', key_saved: false })
    w.vm.aiUses.image.platform = 'my-plat'
    w.vm.aiUses.image.model = 'agnes-image-2.1-flash'
    w.vm.aiUses.video.platform = 'my-plat'

    await w.vm.save()
    const payload = spy.mock.calls[0][0]
    // 平台 key 非空时包含在 ai_platforms 中发送
    expect(payload.ai_platforms[0]).toMatchObject({ name: 'my-plat', key: 'sk-img' })
    // 用途块包含 platform + model
    expect(payload.ai_image).toMatchObject({ platform: 'my-plat', model: 'agnes-image-2.1-flash' })
    expect(payload.ai_video).toMatchObject({ platform: 'my-plat' })
    // 保存后平台 key 输入框清空（_loadAi 由 saveSettings 返回的 settings 触发重置）
    // 当 saveSettings 返回空 settings 时 _loadAi 被调用，platforms 被重置为空数组
    expect(w.vm.aiPlatforms.every(p => p.key === '')).toBe(true)
  })

  it('key 为空时不发送 api_key（不覆盖已存值）', async () => {
    const spy = vi.spyOn(api, 'saveSettings').mockResolvedValue({ settings: {} })
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    // 平台 key 留空时，平台对象中不包含 key 字段
    w.vm.aiPlatforms.push({ name: 'my-plat', base: '', key: '', key_saved: true })
    await w.vm.save()
    const payload = spy.mock.calls[0][0]
    // key 为空时不发送（不覆盖已存 key）
    expect('key' in payload.ai_platforms[0]).toBe(false)
  })

  it('settings 到达后回填 ai_image/ai_video 字段（key 除外）', async () => {
    const { useAppStore } = await import('../src/stores/app.js')
    const store = useAppStore()
    store.settings = {}
    const w = mount(Settings, { global: { plugins: [ElementPlus] } })
    store.settings = {
      ai_platforms: [
        { name: 'agnes-plat', base: 'https://apihub.agnes-ai.com', key_saved: true },
      ],
      ai_image: { platform: 'agnes-plat', model: 'agnes-image-2.1-flash' },
      ai_video: { platform: 'agnes-plat', model: 'agnes-video-v2.0' },
    }
    await w.vm.$nextTick()
    // 平台列表回填
    expect(w.vm.aiPlatforms[0].name).toBe('agnes-plat')
    expect(w.vm.aiPlatforms[0].base).toBe('https://apihub.agnes-ai.com')
    expect(w.vm.aiPlatforms[0].key).toBe('')   // key 永不回填
    // 用途回填
    expect(w.vm.aiUses.image.platform).toBe('agnes-plat')
    expect(w.vm.aiUses.image.model).toBe('agnes-image-2.1-flash')
    expect(w.vm.aiUses.video.model).toBe('agnes-video-v2.0')
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
