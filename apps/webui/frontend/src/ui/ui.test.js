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

import SCard from './SCard.vue'
import SStatCard from './SStatCard.vue'
import SAlert from './SAlert.vue'
import SAvatar from './SAvatar.vue'
import STabs from './STabs.vue'

describe('SCard', () => {
  it('默认 slot + header slot', () => {
    const w = mount(SCard, { slots: { default: '内容', header: '标题' } })
    expect(w.text()).toContain('内容'); expect(w.text()).toContain('标题')
  })
})
describe('SStatCard', () => {
  it('label + value', () => {
    const w = mount(SStatCard, { props: { label: '已连接', value: '2 / 3' } })
    expect(w.text()).toContain('已连接'); expect(w.text()).toContain('2 / 3')
  })
})
describe('SAlert', () => {
  it('variant + 标题 + 操作 slot', () => {
    const w = mount(SAlert, { props: { variant: 'danger', title: '凭证失效' }, slots: { actions: '<b>重新授权</b>' } })
    expect(w.text()).toContain('凭证失效'); expect(w.text()).toContain('重新授权')
    expect(w.classes().join(' ')).toContain('s-alert--danger')
  })
})
describe('SAvatar', () => {
  it('显示首字母', () => {
    const w = mount(SAvatar, { props: { name: 'RU-Store' } })
    expect(w.text()).toContain('R')
  })
})
describe('STabs', () => {
  it('渲染 items + change 事件', async () => {
    const items = [{ key: 'a', label: '全部' }, { key: 'b', label: '待发布' }]
    const w = mount(STabs, { props: { items, activeKey: 'a' } })
    expect(w.text()).toContain('待发布')
    await w.findAll('.s-tabs__item')[1].trigger('click')
    expect(w.emitted('change')[0]).toEqual(['b'])
  })
})
