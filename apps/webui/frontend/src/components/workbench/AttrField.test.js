import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AttrField from './AttrField.vue'

const dictDef = { id: 10, name: '颜色', dictionary_id: 5, is_collection: false, is_required: true }
const multiDef = { id: 11, name: '标签', dictionary_id: 6, is_collection: true, max_value_count: 3 }
const textDef = { id: 30, name: '备注', dictionary_id: 0, is_collection: false }

function factory(def, props = {}) {
  return mount(AttrField, { props: { def, modelValue: [], options: [], loading: false, oversized: false, missing: false, ...props } })
}

describe('AttrField', () => {
  it('字典属性(dictionary_id>0)渲 ElSelect', () => {
    const w = factory(dictDef, { options: [{ id: 101, value: '红' }] })
    expect(w.findComponent({ name: 'ElSelect' }).exists()).toBe(true)
  })

  it('自由文本属性渲 ElInput', () => {
    const w = factory(textDef)
    expect(w.findComponent({ name: 'ElInput' }).exists()).toBe(true)
    expect(w.findComponent({ name: 'ElSelect' }).exists()).toBe(false)
  })

  it('字典单选 pick → emit canonical values 数组', async () => {
    const w = factory(dictDef, { options: [{ id: 101, value: '红' }] })
    w.findComponent({ name: 'ElSelect' }).vm.$emit('change', 101)
    await w.vm.$nextTick()
    const ev = w.emitted('update:modelValue')
    expect(ev[ev.length - 1][0]).toEqual([{ dictionary_value_id: 101, value: '红' }])
  })

  it('字典多选 pick → emit 多条 canonical values', async () => {
    const w = factory(multiDef, { options: [{ id: 1, value: 'a' }, { id: 2, value: 'b' }] })
    w.findComponent({ name: 'ElSelect' }).vm.$emit('change', [1, 2])
    await w.vm.$nextTick()
    const ev = w.emitted('update:modelValue')
    expect(ev[ev.length - 1][0]).toEqual([
      { dictionary_value_id: 1, value: 'a' }, { dictionary_value_id: 2, value: 'b' },
    ])
  })

  it('自由文本输入 → emit [{value}]', async () => {
    const w = factory(textDef)
    w.findComponent({ name: 'ElInput' }).vm.$emit('change', '手填值')
    await w.vm.$nextTick()
    const ev = w.emitted('update:modelValue')
    expect(ev[ev.length - 1][0]).toEqual([{ value: '手填值' }])
  })
})
