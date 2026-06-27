import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
vi.mock('../api.js', () => ({ api: {
  galleryAdd: vi.fn().mockResolvedValue({ id: 7 }),
  galleryRemove: vi.fn().mockResolvedValue({ id: 7 }),
  galleryReorder: vi.fn().mockResolvedValue({ id: 7 }),
  deleteImage: vi.fn().mockResolvedValue({ id: 7 }),
  copyImagesTo: vi.fn().mockResolvedValue({ ok: true, added: { 8: 1 } }),
  uploadMedia: vi.fn().mockResolvedValue({ url: 'http://up/new.jpg' }),
  patchDraft: vi.fn().mockResolvedValue({ draft: { id: 7 } }),
  getDraft: vi.fn().mockResolvedValue({ draft: { id: 8, materials: [
    { id: 81, url: 'http://s/8a.jpg', type: '', source: 'collected', in_gallery: 0, position: 0 },
  ] } }),
} }))
import { api } from '../api.js'
import { useGallery } from './useGallery.js'

beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

function mkDraft() {
  return ref({
    id: 7,
    images: ['http://g/1.jpg', 'http://g/2.jpg'],
    local_images: ['/media/1.jpg', '/media/2.jpg'],
    materials: [
      { id: 1, url: 'http://g/1.jpg', type: '白底', source: 'generated', in_gallery: 1, position: 0 },
      { id: 2, url: 'http://g/2.jpg', type: '场景', source: 'generated', in_gallery: 1, position: 1 },
      { id: 3, url: 'http://m/3.jpg', type: '', source: 'collected', in_gallery: 0, position: 2 },
      { id: 4, url: 'http://m/4.jpg', type: '', source: 'collected', in_gallery: 0, position: 3 },
    ],
  })
}

describe('useGallery', () => {
  it('派生两池：galleryItems(in_gallery 真,按 position) / materialItems(假)', () => {
    const g = useGallery(mkDraft(), { onChange: vi.fn() })
    expect(g.galleryItems.value.map(i => i.id)).toEqual([1, 2])
    expect(g.materialItems.value.map(i => i.id)).toEqual([3, 4])
  })

  it('localUrl：图集 url 命中本地代理,素材回退原 url', () => {
    const g = useGallery(mkDraft(), { onChange: vi.fn() })
    expect(g.localUrl('http://g/1.jpg')).toBe('/media/1.jpg')
    expect(g.localUrl('http://m/3.jpg')).toBe('http://m/3.jpg')
  })

  it('addToGallery 调 api + onChange', async () => {
    const onChange = vi.fn()
    const g = useGallery(mkDraft(), { onChange })
    await g.addToGallery([3])
    expect(api.galleryAdd).toHaveBeenCalledWith(7, [3])
    expect(onChange).toHaveBeenCalled()
  })

  it('removeImage 调 deleteImage + onChange', async () => {
    const onChange = vi.fn()
    const g = useGallery(mkDraft(), { onChange })
    await g.removeImage(2)
    expect(api.deleteImage).toHaveBeenCalledWith(7, 2)
    expect(onChange).toHaveBeenCalled()
  })

  it('moveUp 据 galleryItems 算新序调 reorder', async () => {
    const g = useGallery(mkDraft(), { onChange: vi.fn() })
    await g.moveUp(2)   // [1,2] → 把 2 上移 → [2,1]
    expect(api.galleryReorder).toHaveBeenCalledWith(7, [2, 1])
  })

  it('copyFrom 调 copyImagesTo(源兄弟,urls,[当前])', async () => {
    const onChange = vi.fn()
    const g = useGallery(mkDraft(), { onChange })
    await g.copyFrom(8, ['http://s/8a.jpg'])
    expect(api.copyImagesTo).toHaveBeenCalledWith(8, ['http://s/8a.jpg'], [7])
    expect(onChange).toHaveBeenCalled()
  })

  it('upload：uploadMedia→patchDraft 把新图并进图集', async () => {
    const onChange = vi.fn()
    const g = useGallery(mkDraft(), { onChange })
    await g.upload({ name: 'x.jpg' })
    expect(api.uploadMedia).toHaveBeenCalled()
    const patch = api.patchDraft.mock.calls[0][1]
    expect(patch.images).toEqual(['http://g/1.jpg', 'http://g/2.jpg', 'http://up/new.jpg'])
    expect(onChange).toHaveBeenCalled()
  })

  it('fetchSiblingMaterials 解包 getDraft 的 {draft}', async () => {
    const g = useGallery(mkDraft(), { onChange: vi.fn() })
    const mats = await g.fetchSiblingMaterials(8)
    expect(api.getDraft).toHaveBeenCalledWith(8)
    expect(mats.map(m => m.id)).toEqual([81])
  })

  it('localUrlOf 优先 item.local_url，回退图集 zip', () => {
    const g = useGallery(mkDraft(), { onChange: vi.fn() })
    expect(g.localUrlOf({ url: 'http://m/3.jpg', local_url: '/media/3.jpg' })).toBe('/media/3.jpg')
    expect(g.localUrlOf({ url: 'http://g/1.jpg', local_url: '' })).toBe('/media/1.jpg')
  })
})
