import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

vi.mock('../../api.js', () => ({ api: {
  submitTextJob: vi.fn().mockResolvedValue({ job_id: 10, status: 'queued' }),
  getTextJob: vi.fn().mockResolvedValue({ job_id: 10, status: 'done', current_step: 'attrs' }),
  getLatestTextJob: vi.fn().mockResolvedValue({ job_id: 10, status: 'done', current_step: 'attrs' }),
  designImagePlan: vi.fn().mockResolvedValue({}),
  imagePlan: vi.fn().mockResolvedValue({}),
  makeRichContent: vi.fn().mockResolvedValue({}),
} }))

import { api } from '../../api.js'
import PipelinePanel from './PipelinePanel.vue'
import { useWorkbenchStore } from '../../stores/workbench.js'
import { useAppStore } from '../../stores/app.js'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

function setup() {
  const wb = useWorkbenchStore()
  wb.variants = [
    { id: 1, spec: '红色 200ml', steps: { content: true, images: false }, done: 1 },
    { id: 2, spec: '蓝色 200ml', steps: { content: false, images: false }, done: 0 },
  ]
  wb.currentVariantId = 1
  wb.reload = vi.fn()
  useAppStore().loadDrafts = vi.fn()
  const w = mount(PipelinePanel, { global: { plugins: [ElementPlus] } })
  return { w, wb }
}

describe('PipelinePanel', () => {
  it('渲染流水线和当前变体上下文', () => {
    const { w } = setup()
    expect(w.text()).toContain('AI 生成内容')
    expect(w.text()).toContain('发布')
    expect(w.text()).toContain('正在操作:红色 200ml')
  })

  it('按当前变体显示步骤进度', () => {
    const { w } = setup()
    expect(w.text()).toContain('已完成')
    expect(w.text()).toContain('未开始')
    expect(w.text()).not.toContain('2/2')
    expect(w.text()).not.toContain('1/2')
  })

  it('无当前变体时显示空提示', () => {
    const wb = useWorkbenchStore()
    wb.variants = []
    wb.currentVariantId = null
    const w = mount(PipelinePanel, { global: { plugins: [ElementPlus] } })
    expect(w.text()).toContain('请在上方选择一个变体')
  })

  it('点击发布按钮 emit publish-one', async () => {
    const { w } = setup()
    const btns = w.findAllComponents({ name: 'SButton' })
    const publishBtn = btns.find(b => b.text().includes('发布'))
    await publishBtn.trigger('click')
    expect(w.emitted('publish-one')).toBeTruthy()
    expect(w.emitted('publish-group')).toBeFalsy()
  })

  it('点击重跑提交当前变体 content job 并轮询状态', async () => {
    const { w } = setup()
    const btns = w.findAllComponents({ name: 'SButton' })
    const rerunBtn = btns.find(b => b.text() === '重跑')
    expect(rerunBtn).toBeTruthy()
    await rerunBtn.trigger('click')
    expect(api.submitTextJob).toHaveBeenCalledWith(1)
    expect(api.getTextJob).toHaveBeenCalledWith(10)
  })
})
