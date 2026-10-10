export async function runConcurrent(tasks, concurrency, workerFn, onProgress) {
  const queue = [...tasks]; const results = []; let completed = 0; const total = tasks.length
  const worker = async () => {
    while (queue.length > 0) {
      const task = queue.shift()
      try { results.push({ task, success: true, result: await workerFn(task) }) }
      catch (err) { results.push({ task, success: false, error: err }) }
      finally { completed++; if (onProgress) onProgress(completed, total) }
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, total) || 0 }, worker))
  return results
}
