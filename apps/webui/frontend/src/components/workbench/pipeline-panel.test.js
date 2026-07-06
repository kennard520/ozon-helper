import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

vi.mock('../../api.js', () => ({ api: {
  submitTextJob: vi.fn().mockResolvedValue({ job_id: 10, status: 'queued' }),
  draftPipeline: vi.fn().mockResolvedValue({
    steps: [
      { id: 'collect', label: '采集草稿', status: 'done', message: '已创建草稿', progress: { current: 1, total: 1 } },
      { id: 'ai_text', label: 'AI 文案', status: 'pending', message: '标题、描述、类目与属性' },
      { id: 'preflight', label: '发布前校验', status: 'warning', checks: [{ message: '标题建议优化' }] },
      { id: 'publish', label: '发布到 Ozon', status: 'pending', message: '等待发布' },
    ],
    next: { action: 'run', step_id: 'ai_text', reason: '需要生成文案' },
  }),
  draftPipelineRetry: vi.fn().mockResolvedValue({ job_id: 10, status: 'queued' }),
  draftPipelineSkip: vi.fn().mockResolvedValue({}),
  draftPipelineCancel: vi.fn().mockResolvedValue({}),
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

async function setup() {
  const wb = useWorkbenchStore()
  wb.variants = [
    { id: 1, spec: '红色 200ml', steps: { content: true, images: true, rich: true }, done: 3 },
    { id: 2, spec: '蓝色 200ml', steps: { content: false, images: false }, done: 0 },
  ]
  wb.currentVariantId = 1
  wb.reload = vi.fn()
  useAppStore().loadDrafts = vi.fn()
  const w = mount(PipelinePanel, { global: { plugins: [ElementPlus] } })
  await flushPromises()
  return { w, wb }
}

describe('PipelinePanel', () => {
  it('只渲染四个主功能卡片，不展示后端细分流程', async () => {
    const { w } = await setup()
    expect(w.text()).toContain('AI 智能上架工作台')
    expect(w.text()).toContain('红色 200ml')
    expect(w.findAll('.pp-card').length).toBe(4)
    expect(w.findAll('.pp-row').length).toBe(0)
    expect(w.text()).toContain('AI 生成内容')
    expect(w.text()).toContain('图集/出图')
    expect(w.text()).toContain('富文本')
    expect(w.text()).toContain('发布')
    expect(w.text()).not.toContain('属性映射')
  })

  it('发布卡展示校验风险，但仍然允许点击发布', async () => {
    const { w } = await setup()
    expect(w.text()).toContain('标题建议优化')
    const publishBtn = w.findAllComponents({ name: 'SButton' }).find(b => b.text().includes('发布'))
    expect(publishBtn.props('disabled')).toBe(false)
    await publishBtn.trigger('click')
    expect(w.emitted('publish-one')).toBeTruthy()
  })

  it('无当前变体时显示空提示', async () => {
    const wb = useWorkbenchStore()
    wb.variants = []
    wb.currentVariantId = null
    const w = mount(PipelinePanel, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(w.text()).toContain('请先在上方选择一个变体')
  })

  it('点击 AI 生成内容运行后调用后端 ai_text 步骤', async () => {
    const { w } = await setup()
    const btn = w.findAllComponents({ name: 'SButton' }).find(b => b.text().includes('运行'))
    await btn.trigger('click')
    await flushPromises()
    expect(api.draftPipelineRetry).toHaveBeenCalledWith(1, 'ai_text')
  })
})
