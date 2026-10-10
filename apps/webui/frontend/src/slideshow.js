// 网页端多图幻灯片 → 视频 Blob：纯浏览器原生 Canvas + MediaRecorder。
// 无后台计算、无 npm、无 ffmpeg。优先输出 MP4(H264，Ozon 要的)，浏览器不支持才回退 WebM。

function _loadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.crossOrigin = 'anonymous' // 跨域图试匿名 CORS，避免污染画布(同源忽略)
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('图片加载失败: ' + url))
    img.src = url
  })
}

function _pickMime() {
  const cands = [
    'video/mp4;codecs=avc1.42E01E', 'video/mp4;codecs=avc1', 'video/mp4',
    'video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm',
  ]
  if (typeof window === 'undefined' || !window.MediaRecorder) return ''
  for (const m of cands) {
    try { if (MediaRecorder.isTypeSupported(m)) return m } catch (e) { /* ignore */ }
  }
  return ''
}

// 图按 cover 方式铺满画布(居中裁切)
function _drawCover(ctx, img, W, H, alpha) {
  const ir = img.width / img.height
  const cr = W / H
  let dw, dh, dx, dy
  if (ir > cr) { dh = H; dw = H * ir; dx = (W - dw) / 2; dy = 0 } else { dw = W; dh = W / ir; dx = 0; dy = (H - dh) / 2 }
  ctx.globalAlpha = alpha
  ctx.drawImage(img, dx, dy, dw, dh)
  ctx.globalAlpha = 1
}

// urls: 图片地址数组(尽量用同源 /media，避免跨域污染)。返回 {blob, ext, mime}。
export async function makeSlideshowVideo(urls, opts = {}) {
  const { width = 1080, height = 1440, perImageMs = 2200, fadeMs = 500, fps = 30 } = opts
  const list = (urls || []).filter(Boolean)
  if (!list.length) throw new Error('请至少选 1 张图')
  const mime = _pickMime()
  if (!mime) throw new Error('当前浏览器不支持视频录制(MediaRecorder)')

  const imgs = await Promise.all(list.map(_loadImage))
  // Ozon 视频要 ≥8s：每张停留时长按张数兜底拉满
  const per = Math.max(perImageMs, Math.ceil(8000 / imgs.length))

  const canvas = document.createElement('canvas')
  canvas.width = width; canvas.height = height
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, width, height)

  const stream = canvas.captureStream(fps)
  const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 6_000_000 })
  const chunks = []
  rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data) }
  const stopped = new Promise((res) => { rec.onstop = res })
  rec.start()

  const t0 = performance.now()
  const total = imgs.length * per
  await new Promise((resolve) => {
    function frame() {
      const t = performance.now() - t0
      if (t >= total) { resolve(); return }
      const idx = Math.min(imgs.length - 1, Math.floor(t / per))
      const local = t - idx * per
      ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, width, height)
      if (local < fadeMs && idx > 0) {       // 开头 fadeMs：从上一张淡入
        _drawCover(ctx, imgs[idx - 1], width, height, 1)
        _drawCover(ctx, imgs[idx], width, height, local / fadeMs)
      } else {
        _drawCover(ctx, imgs[idx], width, height, 1)
      }
      requestAnimationFrame(frame)
    }
    requestAnimationFrame(frame)
  })
  rec.stop()
  await stopped

  const blob = new Blob(chunks, { type: mime })
  if (!blob.size) throw new Error('录制失败(画布可能被跨域图污染，建议先把图传到 OSS/本地)')
  return { blob, ext: mime.includes('mp4') ? 'mp4' : 'webm', mime }
}
