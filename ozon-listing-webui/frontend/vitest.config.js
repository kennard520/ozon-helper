import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    globals: true,
    // 给 jsdom 一个真实源，否则 about:blank 是 opaque origin，localStorage 不可用
    environmentOptions: { jsdom: { url: 'http://localhost/' } },
  },
})
