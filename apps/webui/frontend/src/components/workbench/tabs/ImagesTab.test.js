import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
vi.mock('../../../api.js', () => ({ api: {
  galleryAdd: vi.fn().mockResolvedValue({ id: 7 }),
  galleryRemove: vi.fn().mockResolvedValue({ id: 7 }),
  galleryReorder: vi.fn().mockResolvedValue({ id: 7 }),
  deleteImage: vi.fn().mockResolvedValue({ id: 7 }),
  copyImagesTo: vi.fn().mockResolvedValue({ ok: true, added: {} }),
  uploadMedia: vi.fn().mockResolvedValue({ url: 'http://up/n.jpg' }),
  patchDraft: vi.fn().mockResolvedValue({ draft: { id: 7 } }),
  getDraft: vi.fn().mockResolvedValue({ draft: { id: 8, materials: [] } }),
} }))
import { api } from '../../../api.js'
import ImagesTab from './ImagesTab.vue'

const draft = {
  id: 7, images: ['http://g/1.jpg'], local_images: ['/media/1.jpg'],
  materials: [
    { id: 1, url: 'http://g/1.jpg', type: '白底', source: 'generated', in_gallery: 1, position: 0 },
    { id: 3, url: 'http://m/3.jpg', type: '', source: 'collected', in_gallery: 0, position: 1 },
  ],
}

beforeEach(() => { setActivePinia(createPinia()); vi.clearAllMocks() })

function factory() {
  return mount(ImagesTab, {
    props: { draft },
    global: {
      stubs: {
        teleport: true,
        ElSelect: { template: '<div class="el-select-stub"><slot /></div>' },
        ElOption: { template: '<div class="el-option-stub" />' },
      }
    }
  })
}

describe('ImagesTab', () => {
  it('渲图集段(1)+素材段(1)', () => {
    const w = factory()
    expect(w.findAllComponents({ name: 'ImageCard' }).length).toBe(2)
    expect(w.text()).toContain('图集'); expect(w.text()).toContain('素材')
  })
  it('素材「加入图集」触发 galleryAdd', async () => {
    const w = factory()
    const addBtn = w.findAll('button').find(b => b.text().includes('加入图集'))
    await addBtn.trigger('click')
    expect(api.galleryAdd).toHaveBeenCalledWith(7, [3])
  })
})
