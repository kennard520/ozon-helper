import { mount } from '@vue/test-utils'
import ElementPlus, { ElImage } from 'element-plus'
import { describe, it, expect, vi } from 'vitest'
import MediaManager from '../src/components/MediaManager.vue'
import { api } from '../src/api.js'

function makeWrapper() {
  return mount(MediaManager, {
    global: { plugins: [ElementPlus] },
    props: { images: ['a.jpg', 'b.jpg'], videoUrl: 'v.mp4', draftId: 1 },
  })
}

describe('MediaManager (inline)', () => {
  it('removeImage 删掉对应项并 emit 新数组', async () => {
    const w = makeWrapper()
    w.vm.removeImage(0)
    expect(w.emitted()['update:images'][0][0]).toEqual(['b.jpg'])
  })

  it('setCover 把指定图挪到首位', async () => {
    const w = makeWrapper()
    w.vm.setCover(1)
    expect(w.emitted()['update:images'][0][0][0]).toBe('b.jpg')
  })

  it('removeVideo emit 空字符串', async () => {
    const w = makeWrapper()
    w.vm.removeVideo()
    expect(w.emitted()['update:videoUrl'][0][0]).toBe('')
  })

  it('不渲染 el-drawer', () => {
    const w = makeWrapper()
    expect(w.find('.el-drawer').exists()).toBe(false)
  })
})

describe('MediaManager 优先本地副本显示（避开 1688 防盗链；localMap 按 url 不靠下标）', () => {
  const SRC_A = 'https://cbu01.alicdn.com/a.jpg'   // 有本地副本
  const SRC_B = 'https://cbu01.alicdn.com/b.jpg'   // 无本地副本
  const LOCAL_A = '/media/draft-1/00.jpg'

  function makeLocalWrapper() {
    return mount(MediaManager, {
      global: { plugins: [ElementPlus] },
      props: { images: [SRC_A, SRC_B], videoUrl: '', draftId: 1, localMap: { [SRC_A]: LOCAL_A } },
    })
  }

  it('有本地副本的图显示本地路径（避防盗链），无副本的回退源 URL', () => {
    const w = makeLocalWrapper()
    const elImages = w.findAllComponents(ElImage)
    expect(elImages[0].props('src')).toBe(LOCAL_A)   // 1688 图 → 本地副本
    expect(elImages[1].props('src')).toBe(SRC_B)     // 无副本 → 源 url
  })

  it('删首图后剩下的仍按 url 映射本地副本（不下标错位）', () => {
    const w = makeLocalWrapper()
    // 删 SRC_A 后只剩 SRC_B；localMap 按 url 查，SRC_B 无副本仍是源 url（不会错拿 LOCAL_A）
    expect(w.vm.disp(SRC_B)).toBe(SRC_B)
  })

  it('removeImage emit 源 URL 数组', () => {
    const w = makeLocalWrapper()
    w.vm.removeImage(0)
    expect(w.emitted()['update:images'][0][0]).toEqual([SRC_B])
  })
})

describe('MediaManager 多选上传累积不丢图', () => {
  it('并发两次 uploadImage 都进 images（不互相覆盖）', async () => {
    let n = 0
    vi.spyOn(api, 'uploadMedia').mockImplementation(async () => {
      n += 1
      return { url: `/media/draft-1/up-${n}.jpg` }
    })
    const w = mount(MediaManager, {
      global: { plugins: [ElementPlus] },
      props: { images: ['old.jpg'], videoUrl: '', draftId: 1 },
    })
    // 模拟 el-upload multiple 并发调两次 http-request
    await Promise.all([
      w.vm.uploadImage({ file: 'f1' }),
      w.vm.uploadImage({ file: 'f2' }),
    ])
    const emits = w.emitted()['update:images']
    const last = emits[emits.length - 1][0]
    // 旧图保留 + 两张新图都在（不丢、不互相覆盖）
    expect(last).toContain('old.jpg')
    expect(last).toContain('/media/draft-1/up-1.jpg')
    expect(last).toContain('/media/draft-1/up-2.jpg')
    expect(last).toHaveLength(3)
    vi.restoreAllMocks()
  })
})
