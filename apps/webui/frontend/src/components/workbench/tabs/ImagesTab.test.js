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
  aiImage: vi.fn().mockResolvedValue({ ok: true, image: '/media/x.png' }),
  aiImagePrompts: vi.fn().mockResolvedValue({ main: 'p', selling_points: [] }),
  whitenMain: vi.fn().mockResolvedValue({ ok: true }),
  localizeImage: vi.fn().mockResolvedValue({ ok: true }),
  sceneImage: vi.fn().mockResolvedValue({ ok: true }),
  regenImage: vi.fn().mockResolvedValue({ ok: true }),
} }))

import { api } from '../../../api.js'
import { useWorkbenchStore } from '../../../stores/workbench.js'
import ImagesTab from './ImagesTab.vue'

const draft = {
  id: 7,
  source_url: 'https://detail.1688.com/offer/1.html',
  spec: '白色 24码',
  images: ['http://g/1.jpg'],
  local_images: ['/media/1.jpg'],
  materials: [
    { id: 1, url: 'http://g/1.jpg', type: '白底', source: 'generated', in_gallery: 1, position: 0 },
    { id: 3, url: 'http://m/3.jpg', type: '', source: 'collected', in_gallery: 0, position: 1 },
  ],
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    blob: vi.fn().mockResolvedValue(new Blob(['x'], { type: 'image/jpeg' })),
  })
  global.URL.createObjectURL = vi.fn(() => 'blob:test')
  global.URL.revokeObjectURL = vi.fn()
})

function factory() {
  return mount(ImagesTab, {
    props: { draft },
    global: {
      stubs: {
        teleport: true,
        ElSelect: { props: ['modelValue'], emits: ['update:modelValue'], template: '<div class="el-select-stub"><slot /></div>' },
        ElOption: { template: '<div class="el-option-stub" />' },
      },
    },
  })
}

describe('ImagesTab', () => {
  it('渲染图集段和素材段', () => {
    const w = factory()
    expect(w.findAllComponents({ name: 'ImageCard' }).length).toBe(2)
    expect(w.text()).toContain('图集')
    expect(w.text()).toContain('素材库')
  })

  it('出图区只有 AI 生图和复制到别的变体', () => {
    const wb = useWorkbenchStore()
    wb.variants = [{ id: 7, spec: '当前' }, { id: 8, spec: '兄弟' }]
    const w = factory()
    const actions = w.find('.images-tab__actions')
    expect(actions.exists()).toBe(true)
    expect(actions.text()).toContain('AI 生图')
    expect(actions.text()).toContain('复制到别的变体')
  })

  it('点击 AI 生图打开弹窗', async () => {
    const w = factory()
    expect(w.findComponent({ name: 'GenImageModal' }).props('modelValue')).toBe(false)
    const aiBtn = w.find('.images-tab__actions').findAll('button').find(b => b.text().includes('AI 生图'))
    await aiBtn.trigger('click')
    await nextTick()
    expect(w.findComponent({ name: 'GenImageModal' }).props('modelValue')).toBe(true)
  })

  it('复制到别的变体会调用 copyImagesTo', async () => {
    const wb = useWorkbenchStore()
    wb.variants = [{ id: 7, spec: '当前' }, { id: 8, spec: '兄弟' }]
    const w = factory()
    const copyBtn = w.find('.images-tab__actions').findAll('button').find(b => b.text().includes('复制到别的变体'))
    await copyBtn.trigger('click')
    await nextTick()
    expect(w.find('.copy-panel').exists()).toBe(true)
    w.vm.copyTargets = [8]
    await nextTick()
    expect(w.vm.copyUrls).toEqual(['http://g/1.jpg'])
    const confirm = w.find('.copy-panel__foot').findAll('button').find(b => b.text().includes('复制'))
    await confirm.trigger('click')
    await nextTick()
    expect(api.copyImagesTo).toHaveBeenCalledWith(7, ['http://g/1.jpg'], [8])
  })

  it('素材加入图集触发 galleryAdd', async () => {
    const w = factory()
    const addBtn = w.findAll('button').find(b => b.text().includes('加入图集'))
    await addBtn.trigger('click')
    expect(api.galleryAdd).toHaveBeenCalledWith(7, [3])
  })

  it('下载全部会拉取本地图并生成 zip 下载', async () => {
    const w = factory()
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const downloadBtn = w.find('.images-tab__head').findAll('button').find(b => b.text().includes('下载全部'))
    await downloadBtn.trigger('click')
    await nextTick()
    for (let i = 0; i < 20 && w.vm.downloadBusy; i += 1) {
      await new Promise(resolve => setTimeout(resolve, 0))
    }
    expect(global.fetch).toHaveBeenCalledWith('/media/1.jpg', { credentials: 'same-origin' })
    expect(global.URL.createObjectURL).toHaveBeenCalled()
    click.mockRestore()
  })

  it('合规自查徽章显示数量和未知项', () => {
    const w = factory()
    const band = w.find('.compliance')
    expect(band.exists()).toBe(true)
    expect(band.text()).toContain('张数 >= 10')
    expect(band.text()).toContain('比例 3:4 · 未知')
    expect(band.text()).toContain('单张 <= 10MB · 未知')
    const countBadge = w.findAll('.compliance__b').find(b => b.text().includes('张数'))
    expect(countBadge.classes()).toContain('is-warn')
  })

  it('点击放大按钮打开 lightbox，再点击遮罩关闭', async () => {
    const w = factory()
    expect(w.find('.lightbox').exists()).toBe(false)
    await w.find('.img-card__zoom').trigger('click')
    expect(w.find('.lightbox').exists()).toBe(true)
    await w.find('.lightbox').trigger('click')
    expect(w.find('.lightbox').exists()).toBe(false)
  })

  it('clicking material image opens lightbox; select control selects material', async () => {
    const w = factory()
    const cards = w.findAll('.img-card')
    expect(w.vm.selMaterials).toEqual([])
    await cards[1].find('img').trigger('click')
    expect(w.find('.lightbox').exists()).toBe(true)
    expect(w.vm.selMaterials).toEqual([])
    await w.find('.lightbox').trigger('click')
    await cards[1].find('.img-card__select').trigger('click')
    expect(w.vm.selMaterials).toEqual([3])
  })
})
