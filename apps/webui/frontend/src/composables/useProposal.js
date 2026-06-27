import { ref, computed, watch } from 'vue'
import { api } from '../api.js'

const TAG_ATTR = 23171

export function useProposal(draftRef, { onApplied } = {}) {
  const proposal = ref(null)
  const loading = ref(false)
  const fireApplied = (r) => { if (typeof onApplied === 'function') return onApplied(r) }
  const did = () => { const d = draftRef.value || {}; return d.id }

  function initFromDraft(d) {
    const p = d && d.ai_proposal
    proposal.value = p ? JSON.parse(JSON.stringify(p)) : null
  }
  watch(draftRef, (d) => initFromDraft(d), { immediate: true })

  const hasProposal = computed(() => !!proposal.value)
  const attrs = computed(() => (proposal.value && proposal.value.attributes) || [])
  const aiAttrs = computed(() => attrs.value.filter((a) => a.source === 'ai' && Number(a.id) !== TAG_ATTR))
  const missingAttrs = computed(() => attrs.value.filter((a) => a.source === 'missing'))
  const tags = computed(() => {
    const a = attrs.value.find((x) => Number(x.id) === TAG_ATTR)
    return a ? (a.value || '') : ''
  })

  async function patch(body) {
    const id = did(); if (id == null) return
    const r = await api.aiProposalPatch(id, body)
    if (r) proposal.value = r.proposal || null
    return r
  }
  const editField = (key, value) => patch({ op: 'edit_field', key, value })
  const deleteField = (key) => patch({ op: 'delete_field', key })
  const editAttr = (id, value) => patch({ op: 'edit_attr', id, value })
  const deleteAttr = (id) => patch({ op: 'delete_attr', id })
  const editTags = (value) => patch({ op: 'edit_attr', id: TAG_ATTR, value })

  async function apply() {
    const id = did(); if (id == null) return
    loading.value = true
    try {
      const r = await api.aiProposalApply(id)
      await fireApplied(r)
      return r || {}
    } finally { loading.value = false }
  }

  async function discard() {
    await patch({ op: 'discard' })
    return fireApplied()
  }

  async function generate(mode = 'full') {
    const id = did(); if (id == null) return
    loading.value = true
    try {
      const r = mode === 'copy' ? await api.aiCopy(id) : await api.aiGenerate(id)
      await fireApplied(r)
      return r || {}
    } finally { loading.value = false }
  }

  return {
    proposal, loading, hasProposal, aiAttrs, missingAttrs, tags,
    editField, deleteField, editAttr, deleteAttr, editTags,
    apply, discard, generate,
  }
}
