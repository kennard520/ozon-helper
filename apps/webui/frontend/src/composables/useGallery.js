import { computed } from 'vue'
import { api } from '../api.js'

export function useGallery(draftRef, { onChange } = {}) {
  const fire = () => { if (typeof onChange === 'function') return onChange() }

  const materials = computed(() => {
    const d = draftRef.value || {}
    return Array.isArray(d.materials) ? d.materials : []
  })
  const galleryItems = computed(() =>
    materials.value.filter((m) => !!m.in_gallery)
      .slice().sort((a, b) => (a.position || 0) - (b.position || 0)))
  const materialItems = computed(() => materials.value.filter((m) => !m.in_gallery))

  // 图集本地代理：zip draft.images ↔ draft.local_images（同 legacy），素材回退原 url
  const localMap = computed(() => {
    const d = draftRef.value || {}
    const imgs = Array.isArray(d.images) ? d.images : []
    const loc = Array.isArray(d.local_images) ? d.local_images : []
    const out = {}
    imgs.forEach((u, i) => { if (u && loc[i]) out[u] = loc[i] })
    return out
  })
  function localUrl(url) { return localMap.value[url] || url }
  function localUrlOf(item) { return (item && item.local_url) || localUrl(item && item.url) }

  function did() { const d = draftRef.value || {}; return d.id }

  async function addToGallery(ids) { await api.galleryAdd(did(), ids); return fire() }
  async function removeFromGallery(ids) { await api.galleryRemove(did(), ids); return fire() }
  async function reorder(ids) { await api.galleryReorder(did(), ids); return fire() }
  async function removeImage(id) { await api.deleteImage(did(), id); return fire() }

  function _move(id, delta) {
    const order = galleryItems.value.map((i) => i.id)
    const idx = order.indexOf(id)
    const j = idx + delta
    if (idx < 0 || j < 0 || j >= order.length) return null
    const next = order.slice()
    ;[next[idx], next[j]] = [next[j], next[idx]]
    return next
  }
  async function moveUp(id) { const o = _move(id, -1); if (o) { await api.galleryReorder(did(), o); return fire() } }
  async function moveDown(id) { const o = _move(id, 1); if (o) { await api.galleryReorder(did(), o); return fire() } }

  async function copyFrom(siblingId, urls) {
    if (!urls || !urls.length) return
    await api.copyImagesTo(siblingId, urls, [did()])
    return fire()
  }

  async function upload(file) {
    const r = await api.uploadMedia(did(), file, 'image')
    const url = r && r.url
    if (!url) return
    const d = draftRef.value || {}
    const imgs = Array.isArray(d.images) ? d.images.slice() : []
    imgs.push(url)
    await api.patchDraft(did(), { images: imgs })
    return fire()
  }

  async function fetchSiblingMaterials(siblingId) {
    const r = await api.getDraft(siblingId)
    const d = (r && r.draft) ? r.draft : r
    return Array.isArray(d && d.materials) ? d.materials : []
  }

  return {
    galleryItems, materialItems, localUrl, localUrlOf,
    addToGallery, removeFromGallery, reorder, removeImage,
    moveUp, moveDown, copyFrom, upload, fetchSiblingMaterials,
  }
}
