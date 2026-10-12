import { describe, expect, it } from 'vitest'
import Media from '../common/media-resolver.js'

const cardUrl = 'https://mow-basket-cdn-27.geobasket.ru/vol3311/part331107/331107205/info/ru/card.json'

describe('WB media resolver', () => {
  it('builds ordered big gallery images for the exact variant', () => {
    expect(Media.galleryUrls({ media: { photo_count: 2 } }, cardUrl, '331107205')).toEqual([
      'https://mow-basket-cdn-27.geobasket.ru/vol3311/part331107/331107205/images/big/1.webp',
      'https://mow-basket-cdn-27.geobasket.ru/vol3311/part331107/331107205/images/big/2.webp'
    ])
  })

  it.each([
    cardUrl.replace('https:', 'http:'),
    cardUrl.replace('geobasket.ru', 'geobasket.ru.example.com'),
    cardUrl.replace('/331107205/', '/505354016/')
  ])('rejects an unsafe or foreign gallery card source: %s', (unsafeCardUrl) => {
    expect(Media.galleryUrls({ media: { photo_count: 2 } }, unsafeCardUrl, '331107205')).toEqual([])
  })

  it('extracts seller images from rich_v1 content and excludes preview when content exists', () => {
    const rich = {
      content: [
        { type: 'showcase', blocks: [{ image: { src: 'https://content-04.wbbasket.ru/uuid-a/1' } }] },
        { type: 'showcase', blocks: [{ image: { src: 'https://content-01.wbbasket.ru/uuid-b/2.webp' } }] }
      ],
      preview: { src: 'https://content-04.wbbasket.ru/preview/2' }
    }
    expect(Media.richImageUrls(rich)).toEqual([
      'https://content-04.wbbasket.ru/uuid-a/1.webp',
      'https://content-01.wbbasket.ru/uuid-b/2.webp'
    ])
    expect(Media.richJsonUrl(cardUrl)).toBe(cardUrl.replace('/card.json', '/rich_v1.json'))
  })

  it('falls back to a de-duplicated preview only when rich content has no images', () => {
    expect(Media.richImageUrls({
      content: [{ type: 'text', blocks: [{ text: 'description' }] }],
      preview: { src: 'https://content-04.wbbasket.ru/preview/2' }
    })).toEqual(['https://content-04.wbbasket.ru/preview/2.webp'])
  })

  it('filters unsafe rich content sources while retaining valid seller images', () => {
    expect(Media.richImageUrls({
      content: [{ blocks: [
        { image: { src: 'http://content-04.wbbasket.ru/unsafe/1.webp' } },
        { image: { src: 'https://content-04.example.com/unsafe/2.webp' } },
        { image: { src: 'https://images-04.wbbasket.ru/unsafe/3.webp' } },
        { image: { src: 'https://evil-content-04.wbbasket.ru/unsafe/4.webp' } },
        { image: { src: 'https://content-04.wbbasket.ru/safe/5' } }
      ] }],
      preview: { src: 'https://content-04.wbbasket.ru/preview/6' }
    })).toEqual(['https://content-04.wbbasket.ru/safe/5.webp'])
  })

  it('uses only a valid preview after every rich content image is filtered', () => {
    const content = [{ blocks: [
      { image: { src: 'http://content-04.wbbasket.ru/unsafe/1.webp' } },
      { image: { src: 'https://images-04.wbbasket.ru/unsafe/2.webp' } }
    ] }]
    expect(Media.richImageUrls({
      content,
      preview: { src: 'https://content-04.wbbasket.ru/preview/3' }
    })).toEqual(['https://content-04.wbbasket.ru/preview/3.webp'])
    expect(Media.richImageUrls({
      content,
      preview: { src: 'https://evil-content-04.wbbasket.ru/preview/3.webp' }
    })).toEqual([])
  })

  it('rejects a loaded video that belongs to another nm_id', () => {
    const foreign = 'https://mow-videonme-cdn-58.geobasket.ru/vol128/part50535/505354016/mp4/360p/1.mp4'
    expect(Media.videoCandidates({ media: { has_video: true } }, '331107205', [foreign]))
      .not.toContain(foreign)
  })

  it('collects only recursive video fields and predicts qualities from highest to lowest', () => {
    const direct = 'https://videonme-basket-08.wbbasket.ru/vol85/part33110/331107205/mp4/original/1.mp4'
    const ignored = 'https://videonme-basket-08.wbbasket.ru/vol85/part33110/331107205/mp4/240p/1.mp4'
    expect(Media.videoCandidates({
      media: {
        source: ignored,
        nested: { video_files: [{ url: direct }] },
        has_video: true
      }
    }, '331107205', [direct])).toEqual([
      direct,
      'https://videonme-basket-08.wbbasket.ru/vol85/part33110/331107205/mp4/720p/1.mp4',
      'https://videonme-basket-08.wbbasket.ru/vol85/part33110/331107205/mp4/480p/1.mp4',
      'https://videonme-basket-08.wbbasket.ru/vol85/part33110/331107205/mp4/360p/1.mp4'
    ])
  })

  it('selects the first reachable quality candidate', async () => {
    const candidates = ['https://x.wbbasket.ru/331107205/720p/1.mp4', 'https://x.wbbasket.ru/331107205/360p/1.mp4']
    const selected = await Media.resolveVideo(candidates, async (url) => url.includes('/360p/'))
    expect(selected).toBe(candidates[1])
  })

  it('continues probing after a candidate throws', async () => {
    const candidates = ['first.mp4', 'second.mp4', 'third.mp4']
    const selected = await Media.resolveVideo(candidates, async (url) => {
      if (url === candidates[0]) throw new Error('timeout')
      return url === candidates[2]
    })
    expect(selected).toBe(candidates[2])
  })

  it('returns null when every video probe throws or returns false', async () => {
    const candidates = ['first.mp4', 'second.mp4']
    const selected = await Media.resolveVideo(candidates, async (url) => {
      if (url === candidates[0]) throw new Error('timeout')
      return false
    })
    expect(selected).toBeNull()
  })

  it('allows only HTTPS WB media with the required kind-specific binding', () => {
    const gallery = 'https://mow-basket-cdn-27.geobasket.ru/vol3311/part331107/331107205/images/big/1.webp'
    const video = 'https://videonme-basket-08.wbbasket.ru/vol85/part33110/331107205/mp4/720p/1.mp4'
    const rich = 'https://content-04.wbbasket.ru/uuid-a/1.webp'
    expect(Media.isAllowedMediaUrl(gallery, '331107205', 'gallery')).toBe(true)
    expect(Media.isAllowedMediaUrl(video, '331107205', 'video')).toBe(true)
    expect(Media.isAllowedMediaUrl(rich, '331107205', 'rich')).toBe(true)
    expect(Media.isAllowedMediaUrl(gallery.replace('https:', 'http:'), '331107205', 'gallery')).toBe(false)
    expect(Media.isAllowedMediaUrl(gallery.replace('/331107205/', '/3311072050/'), '331107205', 'gallery')).toBe(false)
    expect(Media.isAllowedMediaUrl(rich.replace('content-04', 'images-04'), '331107205', 'rich')).toBe(false)
    expect(Media.isAllowedMediaUrl(rich.replace('content-04', 'evil-content-04'), '331107205', 'rich')).toBe(false)
    expect(Media.isAllowedMediaUrl(rich.replace('wbbasket.ru', 'wbbasket.ru.example.com'), '331107205', 'rich')).toBe(false)
  })
})
