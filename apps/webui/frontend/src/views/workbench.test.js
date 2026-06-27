import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import Workbench from './Workbench.vue'

describe('Workbench 外壳', () => {
  it('渲染三栏容器', () => {
    setActivePinia(createPinia())
    const w = mount(Workbench, { global: { stubs: { DraftListPane: true, VariantCardsPane: true } } })
    expect(w.find('.wb-grid').exists()).toBe(true)
    expect(w.find('.wb-center').exists()).toBe(true)
  })
})
