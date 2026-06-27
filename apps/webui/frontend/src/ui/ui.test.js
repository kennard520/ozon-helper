import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SButton from './SButton.vue'
import SBadge from './SBadge.vue'
import SChip from './SChip.vue'
import SSectionHeader from './SSectionHeader.vue'

describe('SButton', () => {
  it('渲染 slot + variant class + 点击事件', async () => {
    const w = mount(SButton, { props: { variant: 'primary' }, slots: { default: '保存' } })
    expect(w.text()).toContain('保存')
    expect(w.classes().join(' ')).toContain('s-btn--primary')
    await w.trigger('click')
    expect(w.emitted('click')).toBeTruthy()
  })
  it('loading/disabled 时不触发 click', async () => {
    const w = mount(SButton, { props: { loading: true } })
    await w.trigger('click')
    expect(w.emitted('click')).toBeFalsy()
  })
})
describe('SBadge', () => {
  it('variant 映射 class + slot', () => {
    const w = mount(SBadge, { props: { variant: 'success' }, slots: { default: '已连接' } })
    expect(w.text()).toContain('已连接')
    expect(w.classes().join(' ')).toContain('s-badge--success')
  })
})
describe('SChip', () => {
  it('active class + close 事件', async () => {
    const w = mount(SChip, { props: { active: true, closable: true }, slots: { default: '雾灰' } })
    expect(w.classes().join(' ')).toContain('is-active')
    await w.find('.s-chip__close').trigger('click')
    expect(w.emitted('close')).toBeTruthy()
  })
})
describe('SSectionHeader', () => {
  it('标题 + 操作 slot', () => {
    const w = mount(SSectionHeader, { props: { title: '店铺管理' }, slots: { actions: '<button>加</button>' } })
    expect(w.text()).toContain('店铺管理')
    expect(w.text()).toContain('加')
  })
})
