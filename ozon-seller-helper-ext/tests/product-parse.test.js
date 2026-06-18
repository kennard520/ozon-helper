import { describe, it, expect } from 'vitest'
import OzonHelperProduct from '../common/product-parse.js'

const { parseOzonProduct, buildCollectData, applyRubToCny } = OzonHelperProduct

const page1 = {
  widgetStates: {
    'webProductHeading-1-x': JSON.stringify({ title: 'ReNu 360 мл' }),
    'webGallery-2-x': JSON.stringify({
      coverImage: 'https://ir.ozone.ru/cover.jpg',
      images: [{ src: 'https://ir.ozone.ru/1.jpg' }, { src: 'https://ir.ozone.ru/cover.jpg' }],
      videos: [{ url: 'https://v.ozone.ru/x.mp4' }]
    }),
    'webPrice-3-x': JSON.stringify({ cardPrice: '528 ₽', price: '539 ₽', originalPrice: '890 ₽' })
  }
}

const page1chars = {
  widgetStates: {
    'webShortCharacteristics-9-x': JSON.stringify({
      characteristics: [
        { id: 'Height_3', title: { textRs: [{ content: 'Высота, см' }] }, values: [{ text: '54' }] },
        { id: 'Width_4', title: { textRs: [{ content: 'Ширина, см' }] }, values: [{ text: '35' }] },
        { id: 'Length_5', title: { textRs: [{ content: 'Длина, см' }] }, values: [{ text: '24' }] },
        { id: 'Weight_6', title: { textRs: [{ content: 'Вес товара, г' }] }, values: [{ text: '2800' }] }
      ]
    })
  }
}

const page2desc = {
  widgetStates: {
    'webDescription-1-pdpPage2column-2': JSON.stringify({
      richAnnotationJson: { content: [{ blocks: [{ text: { content: ['Первый абзац.', 'Второй абзац.'] } }, { img: { src: 'x' } }] }] }
    })
  }
}

describe('parseOzonProduct', () => {
  it('从 widgetStates 取标题/图(去重,封面在前)/价/视频', () => {
    const p = parseOzonProduct(page1)
    expect(p.title).toBe('ReNu 360 мл')
    expect(p.images).toEqual(['https://ir.ozone.ru/cover.jpg', 'https://ir.ozone.ru/1.jpg'])
    expect(p.price).toBe('528')
    expect(p.old_price).toBe('890')
    expect(p.videos).toEqual(['https://v.ozone.ru/x.mp4'])
    expect(p.video_url).toBe('https://v.ozone.ru/x.mp4')
  })
  it('缺字段不抛异常', () => {
    expect(parseOzonProduct({}).title).toBe('')
    expect(parseOzonProduct(null).images).toEqual([])
  })
})

const page1attrs = {
  widgetStates: {
    'webShortCharacteristics-9-x': JSON.stringify({
      characteristics: [
        { title: { textRs: [{ content: 'Бренд' }] }, values: [{ text: 'Habbarmers' }] },
        { title: { textRs: [{ content: 'Цвет товара' }] }, values: [{ text: 'чёрный' }, { text: 'матовый' }] },
        { title: { textRs: [{ content: 'Тип подключения' }] }, values: [{ text: 'Bluetooth' }] },
        { title: { textRs: [{ content: 'Вес товара, г' }] }, values: [{ text: '180' }] }
      ]
    })
  }
}

const page2full = {
  widgetStates: {
    'webCharacteristics-3-pdpPage2column-2': JSON.stringify({
      totalCount: 6,
      characteristics: [{
        short: [
          { key: 'Sku', name: 'Артикул', values: [{ text: '4318851933' }] },
          { key: 'Type', name: 'Тип', values: [{ text: 'Наушники' }] },
          { key: 'Brand', name: 'Бренд', values: [{ text: 'Habbarmers' }] },
          { key: 'Color', name: 'Цвет товара', values: [{ text: 'чёрный' }, { text: 'матовый' }] },
          { key: 'Weight', name: 'Вес товара, г', values: [{ text: '180' }] },
          { key: 'Height', name: 'Высота, см', values: [{ text: '5' }] }
        ]
      }]
    })
  }
}

describe('parseOzonProduct 全量属性表(webCharacteristics page2)', () => {
  it('抽全量属性、跳过Артикул、克重/尺寸从全量表取', () => {
    const p = parseOzonProduct(page1attrs, page2full)
    // page1attrs(4个高亮) + page2full(全量,去Артикул=5个) 合并去重
    const names = p.characteristics.map((c) => c.name)
    expect(names).toContain('Бренд')
    expect(names).toContain('Цвет товара')
    expect(names).not.toContain('Артикул')      // 竞品货号跳过
    const color = p.characteristics.find((c) => c.name === 'Цвет товара')
    expect(color.value).toBe('чёрный, матовый')
    // 克重/尺寸从全量表取到（高亮表里没有）
    expect(p.weight_g).toBe(180)
    expect(p.height_mm).toBe(50)                 // 5 см → 50 mm
  })
})

describe('parseOzonProduct 全部属性(характеристики)', () => {
  it('抽全部属性为 {name,value}，多值用逗号连，进 source_raw.options', () => {
    const p = parseOzonProduct(page1attrs)
    expect(p.characteristics.length).toBe(4)
    const brand = p.characteristics.find((c) => c.name === 'Бренд')
    expect(brand.value).toBe('Habbarmers')
    const color = p.characteristics.find((c) => c.name === 'Цвет товара')
    expect(color.value).toBe('чёрный, матовый')   // 多值逗号连
    // buildCollectData 把属性放进 attributes(名值对)→后端 draft.attributes，喂 auto-map/AI
    const data = buildCollectData(p)
    expect(data.attributes.length).toBe(4)
    expect(data.attributes.find((o) => o.name === 'Тип подключения').value).toBe('Bluetooth')
  })
  it('无属性时 attributes 为空数组', () => {
    expect(buildCollectData(parseOzonProduct({})).attributes).toEqual([])
  })
})

describe('parseOzonProduct 克重/尺寸/描述', () => {
  it('特征抽克重(g)+长宽高(см→mm)', () => {
    const p = parseOzonProduct(page1chars)
    expect(p.weight_g).toBe(2800)
    expect(p.height_mm).toBe(540)
    expect(p.width_mm).toBe(350)
    expect(p.length_mm).toBe(240)
  })
  it('page2 richAnnotationJson 抽纯文本描述', () => {
    const p = parseOzonProduct({}, page2desc)
    expect(p.description).toBe('Первый абзац.\nВторой абзац.')
  })
  it('page2 richAnnotationJson 的 items 排版(text.items/title.items)也能抽', () => {
    const p2 = {
      widgetStates: {
        'webDescription-9-pdpPage2column-2': JSON.stringify({
          richAnnotationJson: {
            content: [
              {
                blocks: [
                  {
                    title: { items: [{ content: 'Заголовок', type: 'text' }] },
                    text: { items: [{ content: 'Абзац один.', type: 'text' }] }
                  }
                ]
              }
            ]
          }
        })
      }
    }
    expect(parseOzonProduct({}, p2).description).toBe('Заголовок\nАбзац один.')
  })
  it('富文本里的图片(img.src)抽进 detail_images', () => {
    const p2 = {
      widgetStates: {
        'webDescription-9-pdpPage2column-2': JSON.stringify({
          richAnnotationJson: {
            content: [
              { blocks: [{ img: { src: 'https://ir.ozone.ru/d1.jpg' }, text: { items: [{ content: 'txt', type: 'text' }] } }] },
              { blocks: [{ img: { src: 'https://ir.ozone.ru/d2.jpg' } }] }
            ]
          }
        })
      }
    }
    expect(parseOzonProduct({}, p2).detail_images).toEqual(['https://ir.ozone.ru/d1.jpg', 'https://ir.ozone.ru/d2.jpg'])
  })
  it('page2 richAnnotation HTML 字符串(含<br/>)也能抽描述', () => {
    const page2html = {
      widgetStates: {
        'webDescription-9-pdpPage2column-2': JSON.stringify({ richAnnotation: 'Зонт автомат.<br/><br/>Ветроустойчивый.' })
      }
    }
    expect(parseOzonProduct({}, page2html).description).toBe('Зонт автомат.\n\nВетроустойчивый.')
  })
  it('无 page2 时描述为空、尺寸为 null 不报错', () => {
    const p = parseOzonProduct({})
    expect(p.description).toBe('')
    expect(p.weight_g).toBeNull()
  })
})

describe('parseOzonProduct 主题标签(webHashtags)', () => {
  const page2tags = {
    widgetStates: {
      'webHashtags-3685557-pdpPage2column-2': JSON.stringify({
        badges: [
          { text: '#мылоручнойработы' },
          { text: '#натуральноемыло' },
          { text: '#холодныйспособ' }
        ]
      })
    }
  }
  it('page2 webHashtags 抽 badges[].text 进 hashtags', () => {
    expect(parseOzonProduct({}, page2tags).hashtags).toEqual([
      '#мылоручнойработы', '#натуральноемыло', '#холодныйспособ'
    ])
  })
  it('去掉空 text、去重、trim', () => {
    const p2 = {
      widgetStates: {
        'webHashtags-1-pdpPage2column-2': JSON.stringify({
          badges: [{ text: ' #тег ' }, { text: '' }, { text: '#тег' }, { text: null }]
        })
      }
    }
    expect(parseOzonProduct({}, p2).hashtags).toEqual(['#тег'])
  })
  it('无 webHashtags 时 hashtags 为空数组', () => {
    expect(parseOzonProduct(page1).hashtags).toEqual([])
    expect(parseOzonProduct({}).hashtags).toEqual([])
  })
})

describe('buildCollectData', () => {
  it('组装后端 payload 的 data', () => {
    const d = buildCollectData(parseOzonProduct(page1))
    expect(d).toEqual({
      title: 'ReNu 360 мл',
      price: '528',
      old_price: '890',
      images: ['https://ir.ozone.ru/cover.jpg', 'https://ir.ozone.ru/1.jpg'],
      detail_images: [],
      rich_content_json: null,
      video_url: 'https://v.ozone.ru/x.mp4',
      description: '',
      weight_g: null,
      length_mm: null,
      width_mm: null,
      height_mm: null,
      category_path: '',
      variants: [],
      selected_aspects: [],
      hashtags: [],
      attributes: []
    })
  })

  it('buildCollectData 带上 hashtags', () => {
    const p2 = {
      widgetStates: {
        'webHashtags-1-pdpPage2column-2': JSON.stringify({ badges: [{ text: '#тег' }] })
      }
    }
    expect(buildCollectData(parseOzonProduct({}, p2)).hashtags).toEqual(['#тег'])
  })

  it('采原始 richAnnotationJson 进 rich_content_json', () => {
    const p2 = {
      widgetStates: {
        'webDescription-9-pdpPage2column-2': JSON.stringify({
          richAnnotationJson: { content: [{ blocks: [{ text: { items: [{ content: 'x', type: 'text' }] } }] }] }
        })
      }
    }
    const rcj = parseOzonProduct({}, p2).rich_content_json
    expect(rcj).toEqual({ content: [{ blocks: [{ text: { items: [{ content: 'x', type: 'text' }] } }] }] })
  })

  it('面包屑路径 → category_path', () => {
    const p1 = {
      widgetStates: {
        'breadCrumbs-1-x': JSON.stringify({ breadcrumbs: [{ text: 'Аптека' }, { text: 'Оптика' }, { text: 'Растворы' }] })
      }
    }
    expect(parseOzonProduct(p1).category_path).toBe('Аптека/Оптика/Растворы')
  })
})

describe('applyRubToCny 卢布→人民币换算', () => {
  it('按汇率把 price/old_price 换算成 CNY 数字(× rate, 与 publish 路径一致)', () => {
    const d = buildCollectData(parseOzonProduct(page1)) // price '528' / old_price '890' (卢布)
    const out = applyRubToCny(d, 0.08)
    expect(out.price).toBe(42.24) // 528 × 0.08
    expect(out.old_price).toBe(71.2) // 890 × 0.08
  })

  it('变体价(数字)也一并换算', () => {
    const out = applyRubToCny({ price: '500', variants: [{ sku: '1', price: 4274 }, { sku: '2', price: null }] }, 0.08)
    expect(out.price).toBe(40)
    expect(out.variants[0].price).toBe(341.92) // 4274 × 0.08
    expect(out.variants[1].price).toBeNull() // 无价不动
  })

  it('四舍五入到 2 位小数', () => {
    expect(applyRubToCny({ price: '999' }, 0.0784).price).toBe(78.32) // 999 × 0.0784 = 78.3216
  })

  it('汇率缺失/<=0/非法 → 原样返回(不静默写错价)', () => {
    expect(applyRubToCny({ price: '528' }, 0).price).toBe('528')
    expect(applyRubToCny({ price: '528' }, null).price).toBe('528')
    expect(applyRubToCny({ price: '528' }, 'x').price).toBe('528')
  })

  it('空价格不抛异常、保持原样', () => {
    const out = applyRubToCny({ price: '', old_price: '' }, 0.08)
    expect(out.price).toBe('')
    expect(out.old_price).toBe('')
  })
})

describe('parseOzonProduct webAspects 变体', () => {
  it('解析 webAspects → 去重变体列表', () => {
    const p1 = {
      widgetStates: {
        'webAspects-1-x': JSON.stringify({
          aspects: [
            { aspectName: 'Цвет', variants: [
              { sku: '111', link: '/product/a-111/?x=1', availability: 'inStock', data: { searchableText: 'Бежевый', coverImage: 'c1' }, price: 4274 },
              { sku: '222', link: '/product/a-222/', active: true, availability: 'inStock', data: { searchableText: 'Белый' }, price: 4274 }
            ] },
            { aspectName: 'Размер', variants: [
              { sku: '222', link: '/product/a-222/', active: true, availability: 'inStock', data: { searchableText: 'M' }, price: 4274 },
              { sku: '333', link: '/product/a-333/', availability: 'noSuchCombination', data: { searchableText: 'L' }, price: 4570 }
            ] }
          ]
        })
      }
    }
    const vs = parseOzonProduct(p1).variants
    expect(vs.map((v) => v.sku)).toEqual(['111', '222', '333']) // sku 222 去重(只一条)
    expect(vs[0]).toEqual({ sku: '111', label: 'Бежевый', aspect: 'Цвет', link: 'https://www.ozon.ru/product/a-111/?x=1', price: 4274, cover: 'c1', available: true, active: false })
    expect(vs[1].active).toBe(true)
    expect(vs[2].available).toBe(false) // noSuchCombination
  })

  it('无 webAspects 时 variants 为空数组', () => {
    expect(parseOzonProduct(page1).variants).toEqual([])
  })

  it('采当前变体自己选中的颜色/尺寸 selected_aspects', () => {
    const p1 = {
      widgetStates: {
        'webAspects-1-x': JSON.stringify({
          aspects: [
            { aspectName: 'Цвет', aspectKey: 'Color', variants: [
              { sku: '1', data: { searchableText: 'Бежевый' } },
              { sku: '2', active: true, data: { searchableText: 'Белый' } }
            ] },
            { aspectName: 'Размер чемодана', aspectKey: 'SuitcaseSize', variants: [
              { sku: '2', active: true, data: { searchableText: 'M' } },
              { sku: '3', data: { searchableText: 'L' } }
            ] }
          ]
        })
      }
    }
    expect(parseOzonProduct(p1).selected_aspects).toEqual([
      { aspect: 'Цвет', aspect_key: 'Color', value: 'Белый' },
      { aspect: 'Размер чемодана', aspect_key: 'SuitcaseSize', value: 'M' }
    ])
  })
})
