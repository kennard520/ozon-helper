import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ImageCard from './ImageCard.vue'

function factory(props = {}, slots = {}) {
  return mount(ImageCard, {
    props: { url: 'http://x/a.jpg', localUrl: '/media/a.jpg', type: '白底', source: 'generated', ...props },
    slots,
  })
}

describe('ImageCard', () => {
  it('img 用 localUrl 优先', () => {
    const w = factory()
    expect(w.find('img').attributes('src')).toBe('/media/a.jpg')
  })
  it('localUrl 缺时回退 url', () => {
    const w = factory({ localUrl: '' })
    expect(w.find('img').attributes('src')).toBe('http://x/a.jpg')
  })
  it('显示类型徽章', () => {
    expect(factory().text()).toContain('白底')
  })
  it('selected 加选中类', () => {
    const w = factory({ selected: true })
    expect(w.classes().some(c => c.includes('selected') || c.includes('is-sel'))).toBe(true)
  })
  it('actions 插槽渲染', () => {
    const w = factory({}, { actions: '<button class="act">删</button>' })
    expect(w.find('button.act').exists()).toBe(true)
  })
  it('clicking image emits zoom even when selectable', async () => {
    const w = factory({ selectable: true })
    await w.find('img').trigger('click')
    expect(w.emitted('zoom')).toBeTruthy()
    expect(w.emitted('zoom')[0][0]).toBe('/media/a.jpg')
    expect(w.emitted('toggle-select')).toBeFalsy()
  })
  it('clicking select control emits toggle-select only', async () => {
    const w = factory({ selectable: true })
    await w.find('.img-card__select').trigger('click')
    expect(w.emitted('toggle-select')).toBeTruthy()
    expect(w.emitted('zoom')).toBeFalsy()
  })
  it('can hide built-in select control for modal overlays', () => {
    const w = factory({ selectable: true, showSelectControl: false })
    expect(w.find('.img-card__select').exists()).toBe(false)
  })
})
