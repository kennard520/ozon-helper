export function allowedInLite(path) {
  return ['/', '/stores', '/settings', '/login'].includes(path)
}

export function publishLabel(result) {
  if (result?.published) return '发布成功'
  if (result?.errors?.length) return '发布失败'
  if (result?.task_id || result?.submitted) return '已提交，平台处理中'
  return '未发布'
}
