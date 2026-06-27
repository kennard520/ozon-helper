import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
vi.mock('../api.js', () => ({ api: {
  imagePlan: vi.fn().mockResolvedValue({ ok: true, plan: [
    { slot_id: 's0', label: '白底主图', action: 'white', status: 'todo' },
    { slot_id: 's1', label: '场景图', action: 'scene', status: 'applied', candidate_url: 'http://g/s1.jpg' },
  ] }),
  designImagePlan: vi.fn().mockResolvedValue({ ok: true, plan: [
    { slot_id: 's0', label: '白底主图', action: 'white' },
  ], count: 1, fallback: false }),
  generatePlanSlot: vi.fn().mockResolvedValue({ ok: true, slot_id: 's0', candidate: 'http://g/s0.jpg', draft: { id: 7 } }),
} }))
import { api } from '../api.js'
import { useImagePlan } from './useImagePlan.js'

beforeEach(() => { vi.clearAllMocks() })
const draft = () => ref({ id: 7 })

describe('useImagePlan', () => {
  it('loadPlan 调 imagePlan 填 plan + 派生计数', async () => {
    const p = useImagePlan(draft(), { onChange: vi.fn() })
    await p.loadPlan()
    expect(api.imagePlan).toHaveBeenCalledWith(7, false)
    expect(p.plan.value.length).toBe(2)
    expect(p.todoCount.value).toBe(1)
    expect(p.appliedCount.value).toBe(1)
  })

  it('designPlan 调 designImagePlan 后 loadPlan(true)', async () => {
    const p = useImagePlan(draft(), { onChange: vi.fn() })
    await p.designPlan(8)
    expect(api.designImagePlan).toHaveBeenCalledWith(7, 8)
    expect(api.imagePlan).toHaveBeenCalledWith(7, true)
  })

  it('generateSlot 调 generatePlanSlot + onChange + 重 loadPlan', async () => {
    const onChange = vi.fn()
    const p = useImagePlan(draft(), { onChange })
    await p.generateSlot('s0')
    expect(api.generatePlanSlot).toHaveBeenCalledWith(7, 's0')
    expect(onChange).toHaveBeenCalled()
    expect(api.imagePlan).toHaveBeenCalled()
  })

  it('generateAll 仅对 todo 槽串行生成', async () => {
    const p = useImagePlan(draft(), { onChange: vi.fn() })
    await p.loadPlan()            // plan: s0 todo, s1 applied
    await p.generateAll()
    expect(api.generatePlanSlot).toHaveBeenCalledTimes(1)
    expect(api.generatePlanSlot).toHaveBeenCalledWith(7, 's0')
  })

  it('genState 标记生成中', async () => {
    const p = useImagePlan(draft(), { onChange: vi.fn() })
    const pr = p.generateSlot('s0')
    expect(p.genState.s0).toBe(true)
    await pr
    expect(p.genState.s0).toBe(false)
  })
})
