import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import RichContentPreview from '../src/components/RichContentPreview.vue'

const RICH_JSON = {
  content: [
    {
      blocks: [
        {
          img: { src: 'https://example.com/img1.jpg', srcMobile: 'https://example.com/img1m.jpg' },
          title: { content: 'Заголовок блока' },
          text: { items: [{ content: 'Строка первая' }, { content: 'Строка вторая' }] },
        },
        {
          text: { content: ['Абзац А', 'Абзац Б'] },
        },
      ],
    },
  ],
}

describe('RichContentPreview', () => {
  it('рендерит 2 блока для richJson с 2 блоками', () => {
    const w = mount(RichContentPreview, { props: { richJson: RICH_JSON } })
    expect(w.findAll('.rich-block').length).toBe(2)
  })

  it('первый блок содержит img с нужным src', () => {
    const w = mount(RichContentPreview, { props: { richJson: RICH_JSON } })
    const img = w.find('.rich-block img')
    expect(img.exists()).toBe(true)
    expect(img.attributes('src')).toBe('https://example.com/img1.jpg')
  })

  it('первый блок содержит заголовок и текст из items', () => {
    const w = mount(RichContentPreview, { props: { richJson: RICH_JSON } })
    const blocks = w.findAll('.rich-block')
    expect(blocks[0].find('.rich-title').text()).toBe('Заголовок блока')
    expect(blocks[0].find('.rich-text').text()).toContain('Строка первая')
    expect(blocks[0].find('.rich-text').text()).toContain('Строка вторая')
  })

  it('второй блок содержит текст из content-массива', () => {
    const w = mount(RichContentPreview, { props: { richJson: RICH_JSON } })
    const blocks = w.findAll('.rich-block')
    expect(blocks[1].find('.rich-text').text()).toContain('Абзац А')
    expect(blocks[1].find('.rich-text').text()).toContain('Абзац Б')
  })

  it('null richJson показывает .rich-empty', () => {
    const w = mount(RichContentPreview, { props: { richJson: null } })
    expect(w.find('.rich-empty').exists()).toBe(true)
    expect(w.find('.rich-preview').exists()).toBe(false)
  })

  it('пустой объект {} показывает .rich-empty', () => {
    const w = mount(RichContentPreview, { props: { richJson: {} } })
    expect(w.find('.rich-empty').exists()).toBe(true)
  })

  it('content строка в text тоже отображается', () => {
    const rj = { content: [{ blocks: [{ text: { content: 'Просто текст' } }] }] }
    const w = mount(RichContentPreview, { props: { richJson: rj } })
    expect(w.find('.rich-text').text()).toBe('Просто текст')
  })

  it('падения на null-блок не происходит', () => {
    const rj = { content: [{ blocks: [null, { title: { content: 'Ок' } }] }] }
    const w = mount(RichContentPreview, { props: { richJson: rj } })
    expect(w.findAll('.rich-block').length).toBe(1)
  })
})
