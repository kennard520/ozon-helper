# WB Media Downloader Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Chromium MV3 extension that downloads every variant's WB gallery images, seller rich-content images, and product video into isolated folders with on-page progress.

**Architecture:** A WB-only content script owns the floating panel and sends only the current `nm_id` plus observed WB resource hints. Pure CommonJS/browser-global modules resolve cards, rich content, media URLs, paths, plans, and queue state; an event-driven extension service worker validates all URLs, coordinates jobs, persists transient state in `chrome.storage.session`, and calls `chrome.downloads`.

**Tech Stack:** Chromium Manifest V3, vanilla JavaScript, Chrome Extensions `downloads` and `storage` APIs, Vitest 2, jsdom, Node syntax/JSON checks.

## Global Constraints

- Create a new root project at `wb-media-downloader-ext/`; do not modify or depend on `ozon-seller-helper-ext/` at runtime.
- Match only `https://www.wildberries.ru/catalog/*/detail.aspx*` and request only WB/WB-CDN hosts.
- Do not request `cookies`, `tabs`, `<all_urls>`, Ozon, 1688, or localhost permissions.
- Do not call any Ozon WebUI, local service, OSS endpoint, login endpoint, or custom backend.
- Download all variants discovered from `full_colors` and `colors`, always including the current `nm_id`.
- Download gallery images, `rich_v1.json` seller images, and direct product videos; exclude feedback, recommendation, icon, and decorative page media.
- Keep media bound to its own `nm_id`; never use a foreign resource URL as a fallback.
- Write directly through `chrome.downloads` with concurrency `3`, automatic retries `2`, and no ZIP or in-memory media archive.
- Save each run under `WB下载/<title>_imt-<imt_id>/YYYYMMDD-HHmmss/` and write `下载结果.json`.
- Preserve existing unrelated workspace changes; each task stages only paths listed in that task.
- Follow strict RED-GREEN-REFACTOR: every new behavior starts with a failing test whose failure is observed before production code is written.

---

## File Map

- `wb-media-downloader-ext/manifest.json`: MV3 entry points and least-privilege permissions.
- `wb-media-downloader-ext/package.json`: Vitest/jsdom development commands only; no runtime bundle step.
- `wb-media-downloader-ext/common/wb-card.js`: product-page parsing, card URL candidates, card resolution, variant discovery and labels.
- `wb-media-downloader-ext/common/media-resolver.js`: gallery, rich-content and per-`nm_id` video candidate extraction and URL validation.
- `wb-media-downloader-ext/common/file-path.js`: Windows-safe path segments, timestamps and file extensions.
- `wb-media-downloader-ext/common/download-plan.js`: deterministic per-variant directory and media item planning.
- `wb-media-downloader-ext/common/download-queue.js`: concurrency, retry, cancel and progress state machine independent of Chrome APIs.
- `wb-media-downloader-ext/common/job-controller.js`: complete scan/plan/download orchestration with injected browser adapters.
- `wb-media-downloader-ext/service-worker.js`: Chrome message, storage and downloads adapters; no domain parsing logic.
- `wb-media-downloader-ext/content/view.js`: floating panel DOM and render states.
- `wb-media-downloader-ext/content/downloader.js`: page bootstrap, resource hints and runtime messaging.
- `wb-media-downloader-ext/content/downloader.css`: scoped floating-panel styles.
- `wb-media-downloader-ext/tests/*.test.js`: unit and contract tests for every module.
- `wb-media-downloader-ext/README.md`: local installation, permissions, output layout and troubleshooting.

### Task 1: Standalone project, manifest boundary, and WB page detection

**Files:**
- Create: `wb-media-downloader-ext/package.json`
- Create: `wb-media-downloader-ext/.gitignore`
- Create: `wb-media-downloader-ext/manifest.json`
- Create: `wb-media-downloader-ext/common/wb-card.js`
- Create: `wb-media-downloader-ext/tests/manifest.test.js`
- Create: `wb-media-downloader-ext/tests/wb-card.test.js`

**Interfaces:**
- Produces: `WbMediaCard.nmFromUrl(url) -> string|null`
- Produces: `WbMediaCard.isProductPage(url) -> boolean`
- Produces: `WbMediaCard.volPart(nm) -> {vol:number, part:number}`
- Produces: MV3 manifest with scripts ordered for browser globals and permissions `downloads`, `storage`.

- [ ] **Step 1: Write the failing project-boundary tests**

```js
// tests/manifest.test.js
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'

const manifest = JSON.parse(fs.readFileSync(new URL('../manifest.json', import.meta.url), 'utf8'))

describe('manifest security boundary', () => {
  it('is WB-only and requests no backend or account permissions', () => {
    expect(manifest.manifest_version).toBe(3)
    expect(manifest.permissions.sort()).toEqual(['downloads', 'storage'])
    expect(manifest.host_permissions).toEqual([
      'https://www.wildberries.ru/*',
      'https://*.wbbasket.ru/*',
      'https://*.geobasket.ru/*',
      'https://*.wb.ru/*'
    ])
    expect(JSON.stringify(manifest)).not.toMatch(/ozon|1688|localhost|<all_urls>|cookies|tabs/i)
    expect(manifest.content_scripts[0].matches).toEqual([
      'https://www.wildberries.ru/catalog/*/detail.aspx*'
    ])
  })
})
```

```js
// tests/wb-card.test.js
import { describe, expect, it } from 'vitest'
import Card from '../common/wb-card.js'

describe('WB page identity', () => {
  it('extracts nm_id only from a WB product detail URL', () => {
    expect(Card.nmFromUrl('https://www.wildberries.ru/catalog/331107205/detail.aspx')).toBe('331107205')
    expect(Card.nmFromUrl('https://www.wildberries.ru/catalog/platya')).toBeNull()
    expect(Card.isProductPage('https://www.wildberries.ru/catalog/331107205/detail.aspx?targetUrl=GP')).toBe(true)
    expect(Card.isProductPage('https://www.wildberries.ru/catalog/0/search.aspx?search=test')).toBe(false)
  })

  it('derives vol and part from nm_id', () => {
    expect(Card.volPart('331107205')).toEqual({ vol: 3311, part: 331107 })
  })
})
```

- [ ] **Step 2: Run the tests and observe RED**

Run: `cd wb-media-downloader-ext && npm test -- manifest.test.js wb-card.test.js`

Expected: FAIL because `manifest.json` and `common/wb-card.js` do not exist.

- [ ] **Step 3: Add the minimal standalone project and page parser**

```json
// package.json
{
  "name": "wb-media-downloader-ext",
  "version": "0.1.0",
  "private": true,
  "description": "Standalone WB product image and video downloader extension",
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "devDependencies": {
    "jsdom": "^26.1.0",
    "vitest": "^2.1.8"
  }
}
```

```json
// manifest.json
{
  "manifest_version": 3,
  "name": "WB 图片视频下载器",
  "version": "0.1.0",
  "description": "一键下载 WB 商品全部变体的轮播图、详情图和视频",
  "background": { "service_worker": "service-worker.js" },
  "permissions": ["downloads", "storage"],
  "host_permissions": [
    "https://www.wildberries.ru/*",
    "https://*.wbbasket.ru/*",
    "https://*.geobasket.ru/*",
    "https://*.wb.ru/*"
  ],
  "content_scripts": [{
    "matches": ["https://www.wildberries.ru/catalog/*/detail.aspx*"],
    "js": [
      "common/wb-card.js",
      "common/media-resolver.js",
      "common/file-path.js",
      "common/download-plan.js",
      "content/view.js",
      "content/downloader.js"
    ],
    "css": ["content/downloader.css"],
    "run_at": "document_idle"
  }],
  "action": { "default_title": "WB 图片视频下载器" }
}
```

```js
// common/wb-card.js — initial exports
;(function (root, factory) {
  const api = factory()
  if (typeof module === 'object' && module.exports) module.exports = api
  root.WbMediaCard = api
})(typeof globalThis !== 'undefined' ? globalThis : self, function () {
  function nmFromUrl(url) {
    const match = String(url || '').match(/^https:\/\/www\.wildberries\.ru\/catalog\/(\d+)\/detail\.aspx(?:[?#]|$)/i)
    return match ? match[1] : null
  }

  function isProductPage(url) {
    return nmFromUrl(url) !== null
  }

  function volPart(nm) {
    const value = Number.parseInt(nm, 10)
    return { vol: Math.floor(value / 100000), part: Math.floor(value / 1000) }
  }

  return { nmFromUrl, isProductPage, volPart }
})
```

Create `.gitignore` containing exactly:

```text
node_modules/
coverage/
```

Run `npm install` in `wb-media-downloader-ext/` to generate `package-lock.json`.

- [ ] **Step 4: Run the tests and observe GREEN**

Run: `cd wb-media-downloader-ext && npm test -- manifest.test.js wb-card.test.js`

Expected: 2 test files pass; no Ozon/backend permission is present.

- [ ] **Step 5: Commit the standalone boundary**

```bash
git add wb-media-downloader-ext/package.json wb-media-downloader-ext/package-lock.json wb-media-downloader-ext/.gitignore wb-media-downloader-ext/manifest.json wb-media-downloader-ext/common/wb-card.js wb-media-downloader-ext/tests/manifest.test.js wb-media-downloader-ext/tests/wb-card.test.js
git commit -m "feat(wb-download): scaffold standalone extension"
```

### Task 2: Card resolution, variant discovery, and labels

**Files:**
- Modify: `wb-media-downloader-ext/common/wb-card.js`
- Modify: `wb-media-downloader-ext/tests/wb-card.test.js`

**Interfaces:**
- Consumes: `volPart(nm)` from Task 1.
- Produces: `cardJsonUrlFromEntries(entries, nm) -> string|null`
- Produces: `basketCardUrls(nm) -> Array<{host:string,url:string}>`
- Produces: `resolveCard(nm, hintUrl, fetchJson) -> Promise<{card:object,cardUrl:string,host:string}>`
- Produces: `variantIds(card, currentNm) -> string[]`
- Produces: `variantLabel(card, index) -> string`

- [ ] **Step 1: Add failing tests for page-loaded card preference and all variants**

```js
it('prefers a page-loaded card URL that belongs to the same nm_id', () => {
  const entries = [
    'https://mow-basket-cdn-22.geobasket.ru/vol11905/part1190575/1190575807/info/ru/card.json',
    'https://mow-basket-cdn-22.geobasket.ru/vol11905/part1190575/1190575806/info/ru/card.json'
  ]
  expect(Card.cardJsonUrlFromEntries(entries, '1190575806')).toBe(entries[1])
})

it('discovers and de-duplicates every color variant while retaining current nm_id', () => {
  const card = {
    full_colors: [{ nm_id: 399656234 }, { nm_id: 737964991 }, { nm_id: 1190575807 }],
    colors: [399656234, 1190575807, 1190575806]
  }
  expect(Card.variantIds(card, '1190575806')).toEqual([
    '399656234', '737964991', '1190575807', '1190575806'
  ])
})

it('resolves the validated hint before generated fallback candidates', async () => {
  const calls = []
  const hint = 'https://mow-basket-cdn-22.geobasket.ru/vol11905/part1190575/1190575806/info/ru/card.json'
  const result = await Card.resolveCard('1190575806', hint, async (url) => {
    calls.push(url)
    return { nm_id: 1190575806, imt_id: 1390661929, nm_colors_names: 'черный' }
  })
  expect(calls).toEqual([hint])
  expect(result.host).toBe('mow-basket-cdn-22.geobasket.ru')
  expect(Card.variantLabel(result.card, 0)).toBe('черный')
})
```

- [ ] **Step 2: Run the focused tests and observe RED**

Run: `cd wb-media-downloader-ext && npm test -- wb-card.test.js`

Expected: FAIL because the five new functions are not exported.

- [ ] **Step 3: Implement deterministic card resolution**

Add these concrete behaviors to the `WbMediaCard` factory:

```js
function variantIds(card, currentNm) {
  const out = []
  const seen = new Set()
  const add = (value) => {
    const raw = value && typeof value === 'object' ? (value.nm_id || value.id || value.nm) : value
    const id = String(raw || '').trim()
    if (!/^\d+$/.test(id) || seen.has(id)) return
    seen.add(id)
    out.push(id)
  }
  ;((card && card.full_colors) || []).forEach(add)
  ;((card && card.colors) || []).forEach(add)
  add(currentNm || (card && card.nm_id))
  return out
}

function variantLabel(card, index) {
  const value = String((card && card.nm_colors_names) || '').trim()
  return value || `变体${String(index + 1).padStart(2, '0')}`
}

function cardJsonUrlFromEntries(entries, nm) {
  const id = String(nm || '')
  for (let index = (entries || []).length - 1; index >= 0; index--) {
    const raw = typeof entries[index] === 'string' ? entries[index] : entries[index] && entries[index].name
    try {
      const url = new URL(raw)
      if (/\.(?:wbbasket|geobasket|wb)\.ru$/i.test(url.hostname) &&
          url.pathname.endsWith(`/${id}/info/ru/card.json`)) return url.href
    } catch (_) { /* invalid resource entry */ }
  }
  return null
}
```

Port the already-tested `basketCardUrls(nm)` range calculation from `ozon-seller-helper-ext/common/wb.js` without importing that file. Add `isAllowedCardUrl(url, nm)` that requires HTTPS, a WB host, and exact `/${nm}/info/ru/card.json`. Implement `resolveCard` as:

```js
async function resolveCard(nm, hintUrl, fetchJson) {
  const candidates = []
  if (isAllowedCardUrl(hintUrl, nm)) candidates.push(hintUrl)
  for (const item of basketCardUrls(nm)) if (!candidates.includes(item.url)) candidates.push(item.url)
  let lastError = null
  for (const cardUrl of candidates) {
    try {
      const card = await fetchJson(cardUrl)
      if (card && String(card.nm_id || nm) === String(nm)) {
        return { card, cardUrl, host: new URL(cardUrl).hostname }
      }
    } catch (error) { lastError = error }
  }
  throw new Error(`无法读取 WB 商品 ${nm}: ${lastError ? lastError.message : 'card.json 不可用'}`)
}
```

Export every new function from the factory.

- [ ] **Step 4: Run focused and existing copied-behavior tests**

Run: `cd wb-media-downloader-ext && npm test -- wb-card.test.js`

Expected: PASS, including the real current-domain shape `mow-basket-cdn-*.geobasket.ru`.

- [ ] **Step 5: Commit card and variant discovery**

```bash
git add wb-media-downloader-ext/common/wb-card.js wb-media-downloader-ext/tests/wb-card.test.js
git commit -m "feat(wb-download): resolve cards and variants"
```

### Task 3: Gallery, rich-content, and per-variant video resolution

**Files:**
- Create: `wb-media-downloader-ext/common/media-resolver.js`
- Create: `wb-media-downloader-ext/tests/media-resolver.test.js`

**Interfaces:**
- Consumes: `{card, cardUrl, host}` from `resolveCard`.
- Produces: `galleryUrls(card, cardUrl, nm) -> string[]`
- Produces: `richJsonUrl(cardUrl) -> string`
- Produces: `richImageUrls(richJson) -> string[]`
- Produces: `videoCandidates(card, nm, observedUrls) -> string[]`
- Produces: `resolveVideo(candidates, probe) -> Promise<string|null>`
- Produces: `isAllowedMediaUrl(url, nm, kind) -> boolean`

- [ ] **Step 1: Write failing media-source tests from real WB payload shapes**

```js
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

  it('rejects a loaded video that belongs to another nm_id', () => {
    const foreign = 'https://mow-videonme-cdn-58.geobasket.ru/vol128/part50535/505354016/mp4/360p/1.mp4'
    expect(Media.videoCandidates({ media: { has_video: true } }, '331107205', [foreign]))
      .not.toContain(foreign)
  })

  it('selects the first reachable quality candidate', async () => {
    const candidates = ['https://x.wbbasket.ru/331107205/720p/1.mp4', 'https://x.wbbasket.ru/331107205/360p/1.mp4']
    const selected = await Media.resolveVideo(candidates, async (url) => url.includes('/360p/'))
    expect(selected).toBe(candidates[1])
  })
})
```

- [ ] **Step 2: Run the test and observe RED**

Run: `cd wb-media-downloader-ext && npm test -- media-resolver.test.js`

Expected: FAIL because `common/media-resolver.js` does not exist.

- [ ] **Step 3: Implement media extraction without page-wide image scraping**

Implement a UMD/CommonJS factory named `WbMediaResolver`. The core rich and gallery logic must be exactly bounded as follows:

```js
function galleryUrls(card, cardUrl, nm) {
  const url = new URL(cardUrl)
  const count = Math.max(0, Number.parseInt(card && card.media && card.media.photo_count, 10) || 0)
  const prefix = url.pathname.replace(`/${nm}/info/ru/card.json`, `/${nm}/images/big`)
  return Array.from({ length: count }, (_, index) => `${url.origin}${prefix}/${index + 1}.webp`)
}

function richJsonUrl(cardUrl) {
  return String(cardUrl).replace(/\/card\.json(?:\?.*)?$/, '/rich_v1.json')
}

function ensureWebp(url) {
  return /\.[a-z0-9]{2,5}(?:[?#]|$)/i.test(url) ? url : `${url}.webp`
}

function richImageUrls(richJson) {
  const content = Array.isArray(richJson && richJson.content) ? richJson.content : []
  const out = []
  for (const widget of content) {
    for (const block of (widget && widget.blocks) || []) {
      const src = block && block.image && block.image.src
      if (typeof src === 'string' && src) out.push(ensureWebp(src))
    }
  }
  if (!out.length && richJson && richJson.preview && richJson.preview.src) out.push(ensureWebp(richJson.preview.src))
  return [...new Set(out)]
}
```

For video, recursively inspect only object keys containing `video`, accept direct `.mp4` strings only when the path contains `/${nm}/`, then append observed URLs with the same rule. When `card.media.has_video` is true, append predicted candidates for `720p`, `480p`, and `360p` using the established WB video `vol = nm % 144`, `part = floor(nm / 10000)`, and `videonme-basket-NN.wbbasket.ru` bucket mapping from `ozon-seller-helper-ext/common/wb.js`. `resolveVideo` probes candidates in order and returns the first `true` result.

`isAllowedMediaUrl` must require HTTPS, a hostname ending in `.wbbasket.ru`, `.geobasket.ru`, or `.wb.ru`, and:

- gallery/video: path contains exact `/${nm}/`;
- rich: hostname contains `content-` and path ends in an image extension.

- [ ] **Step 4: Run tests and verify current live resource examples**

Run: `cd wb-media-downloader-ext && npm test -- media-resolver.test.js`

Expected: PASS. Then run read-only probes:

```powershell
curl.exe -L --max-time 15 -sS -o NUL -w '%{http_code}' 'https://mow-basket-cdn-27.geobasket.ru/vol3311/part331107/331107205/info/ru/rich_v1.json'
curl.exe -L --max-time 15 -sS -o NUL -w '%{http_code}' 'https://videonme-basket-08.wbbasket.ru/vol85/part33110/331107205/mp4/360p/1.mp4'
```

Expected at implementation time: each known-good sample returns `200`; if WB has retired the sample, replace the fixture only after capturing an equivalent current page-loaded URL and recording it in the test comment.

- [ ] **Step 5: Commit media resolvers**

```bash
git add wb-media-downloader-ext/common/media-resolver.js wb-media-downloader-ext/tests/media-resolver.test.js
git commit -m "feat(wb-download): resolve variant media"
```

### Task 4: Safe paths and deterministic download plans

**Files:**
- Create: `wb-media-downloader-ext/common/file-path.js`
- Create: `wb-media-downloader-ext/common/download-plan.js`
- Create: `wb-media-downloader-ext/tests/file-path.test.js`
- Create: `wb-media-downloader-ext/tests/download-plan.test.js`

**Interfaces:**
- Produces: `sanitizeSegment(value, fallback, maxLength=80) -> string`
- Produces: `formatBatchTime(date) -> YYYYMMDD-HHmmss`
- Produces: `extensionFromUrl(url, fallback) -> string`
- Produces: `buildBatchRoot(product, date) -> string`
- Produces: `buildDownloadPlan(product, variants, date) -> DownloadItem[]`
- `DownloadItem`: `{id,nm,kind,url,filename,status,attempts,error,handle?}`; `handle` is the persisted Chrome download ID after a file starts.

- [ ] **Step 1: Write failing path and plan tests**

```js
// tests/file-path.test.js
import { describe, expect, it } from 'vitest'
import Path from '../common/file-path.js'

it('removes Windows-invalid names, trailing dots, and reserved devices', () => {
  expect(Path.sanitizeSegment('红色:42/44. ')).toBe('红色_42_44')
  expect(Path.sanitizeSegment('CON')).toBe('_CON')
})

it('formats a stable local batch timestamp', () => {
  expect(Path.formatBatchTime(new Date(2026, 6, 14, 15, 30, 9))).toBe('20260714-153009')
})
```

```js
// tests/download-plan.test.js
import { expect, it } from 'vitest'
import Plan from '../common/download-plan.js'

it('creates isolated gallery, rich, and video folders per variant', () => {
  const items = Plan.buildDownloadPlan(
    { title: '连衣裙', imtId: '1390661929' },
    [{ nm: '1190575806', label: '黑色', gallery: ['https://a.wbbasket.ru/1190575806/1.webp'], rich: ['https://content-1.wbbasket.ru/x/1.webp'], videos: ['https://v.wbbasket.ru/1190575806/1.mp4'] }],
    new Date(2026, 6, 14, 15, 30, 9)
  )
  expect(items.map((item) => item.filename)).toEqual([
    'WB下载/连衣裙_imt-1390661929/20260714-153009/01_黑色_nm-1190575806/轮播图/01.webp',
    'WB下载/连衣裙_imt-1390661929/20260714-153009/01_黑色_nm-1190575806/详情图/01.webp',
    'WB下载/连衣裙_imt-1390661929/20260714-153009/01_黑色_nm-1190575806/视频/01.mp4'
  ])
})
```

- [ ] **Step 2: Run both tests and observe RED**

Run: `cd wb-media-downloader-ext && npm test -- file-path.test.js download-plan.test.js`

Expected: FAIL because both modules are missing.

- [ ] **Step 3: Implement safe segments and plan construction**

`sanitizeSegment` must replace `[<>:"/\\|?*\x00-\x1F]` runs with `_`, trim spaces/dots, prefix Windows device names `CON|PRN|AUX|NUL|COM1..9|LPT1..9` with `_`, truncate to `maxLength`, and return the fallback when empty.

`buildDownloadPlan` must enumerate variants in input order and media in source order:

```js
function addKind(items, base, nm, kind, folder, urls, fallbackExt) {
  ;[...new Set(urls || [])].forEach((url, index) => {
    const ext = WbMediaPath.extensionFromUrl(url, fallbackExt)
    items.push({
      id: `${nm}:${kind}:${index + 1}`,
      nm, kind, url,
      filename: `${base}/${folder}/${String(index + 1).padStart(2, '0')}.${ext}`,
      status: 'pending', attempts: 0, error: ''
    })
  })
}
```

Use `gallery -> 轮播图 -> webp`, `rich -> 详情图 -> webp`, and `videos -> 视频 -> mp4`. Limit every segment to 80 characters and the complete relative filename to 220 characters by shortening only the product-title segment before changing stable IDs.

- [ ] **Step 4: Run tests and observe GREEN**

Run: `cd wb-media-downloader-ext && npm test -- file-path.test.js download-plan.test.js`

Expected: PASS with deterministic Chinese directory names.

- [ ] **Step 5: Commit path and plan logic**

```bash
git add wb-media-downloader-ext/common/file-path.js wb-media-downloader-ext/common/download-plan.js wb-media-downloader-ext/tests/file-path.test.js wb-media-downloader-ext/tests/download-plan.test.js
git commit -m "feat(wb-download): plan safe media paths"
```

### Task 5: Retryable, cancellable download queue

**Files:**
- Create: `wb-media-downloader-ext/common/download-queue.js`
- Create: `wb-media-downloader-ext/tests/download-queue.test.js`

**Interfaces:**
- Produces: `runDownloadQueue(items, options) -> Promise<{items,completed,failed,cancelled}>`
- `options.start(item) -> Promise<{handle:string|number, completion:Promise<void>}>` starts a download and immediately exposes its cancellable handle.
- Remaining options: `{cancel(handle), onProgress(snapshot), concurrency:3, retries:2, signal}`.

- [ ] **Step 1: Write failing queue behavior tests**

```js
import { describe, expect, it } from 'vitest'
import Queue from '../common/download-queue.js'

describe('download queue', () => {
  it('never exceeds three active downloads and retries twice', async () => {
    let active = 0
    let peak = 0
    const attempts = new Map()
    const items = Array.from({ length: 5 }, (_, index) => ({ id: String(index), status: 'pending', attempts: 0 }))
    const result = await Queue.runDownloadQueue(items, {
      concurrency: 3,
      retries: 2,
      start: async (item) => {
        active++
        peak = Math.max(peak, active)
        const count = (attempts.get(item.id) || 0) + 1
        attempts.set(item.id, count)
        return {
          handle: `download-${item.id}-${count}`,
          completion: Promise.resolve().then(() => {
            active--
            if (item.id === '0' && count < 3) throw new Error('temporary')
          })
        }
      },
      cancel: async () => {},
      onProgress: () => {}
    })
    expect(peak).toBeLessThanOrEqual(3)
    expect(attempts.get('0')).toBe(3)
    expect(result.completed).toBe(5)
  })
})
```

- [ ] **Step 2: Run the queue test and observe RED**

Run: `cd wb-media-downloader-ext && npm test -- download-queue.test.js`

Expected: FAIL because the queue module does not exist.

- [ ] **Step 3: Implement workers, retry accounting, and abort behavior**

Implement `runDownloadQueue` with a shared next-index counter and `Math.min(concurrency, items.length)` async workers. Each worker awaits `start(item)`, stores the returned `handle` on the item, and then awaits `completion`. Each item transition is `pending -> downloading -> complete|failed|cancelled`. Count the initial attempt plus two retries. After every transition call `onProgress` with a cloned snapshot containing `total`, `completed`, `failed`, `cancelled`, `active`, and `items`.

When `signal.aborted` becomes true, stop claiming new items, call injected `cancel(handle)` for active handles, mark untouched items `cancelled`, and resolve only after active workers settle. Do not delete completed files.

- [ ] **Step 4: Add cancellation test and verify GREEN**

Add a second test that aborts after the first `onProgress` snapshot with `active > 0`, asserts `cancel` was called, asserts at least one untouched item is `cancelled`, and asserts completed items remain `complete`.

Run: `cd wb-media-downloader-ext && npm test -- download-queue.test.js`

Expected: PASS for concurrency, retries and cancellation.

- [ ] **Step 5: Commit queue behavior**

```bash
git add wb-media-downloader-ext/common/download-queue.js wb-media-downloader-ext/tests/download-queue.test.js
git commit -m "feat(wb-download): add resilient download queue"
```

### Task 6: Job controller and Chrome service-worker adapters

**Files:**
- Create: `wb-media-downloader-ext/common/job-controller.js`
- Create: `wb-media-downloader-ext/service-worker.js`
- Create: `wb-media-downloader-ext/tests/job-controller.test.js`
- Create: `wb-media-downloader-ext/tests/service-worker-contract.test.js`

**Interfaces:**
- Consumes: card/media/path/plan/queue modules from Tasks 2-5.
- Produces: `createJobController(deps) -> {start,stop,retryFailed,getState,restore}`.
- Produces messages: `START_JOB`, `STOP_JOB`, `RETRY_FAILED`, `GET_JOB_STATE`.
- Produces broadcasts: `JOB_STATE` with `{jobId,nm,phase,totalVariants,resolvedVariants,totalFiles,completed,failed,cancelled,currentVariant,error}`.

- [ ] **Step 1: Write failing orchestration and message-contract tests**

```js
// tests/job-controller.test.js
import { expect, it, vi } from 'vitest'
import Jobs from '../common/job-controller.js'

it('resolves every sibling separately and downloads one combined plan', async () => {
  const resolved = []
  const cards = {
    '10': { card: { nm_id: 10, imt_id: 99, imt_name: 'Dress', full_colors: [{ nm_id: 11 }], colors: [10], nm_colors_names: 'white', media: { photo_count: 1 } }, cardUrl: 'https://basket-01.wbbasket.ru/vol0/part0/10/info/ru/card.json', host: 'basket-01.wbbasket.ru' },
    '11': { card: { nm_id: 11, imt_id: 99, imt_name: 'Dress', nm_colors_names: 'black', media: { photo_count: 1, has_video: true } }, cardUrl: 'https://basket-01.wbbasket.ru/vol0/part0/11/info/ru/card.json', host: 'basket-01.wbbasket.ru' }
  }
  const controller = Jobs.createJobController({
    now: () => new Date(2026, 6, 14, 15, 30, 9),
    resolveCard: async (nm) => { resolved.push(nm); return cards[nm] },
    fetchJson: async (url) => url.endsWith('/rich_v1.json') ? { content: [] } : {},
    probe: async () => true,
    runQueue: async (items, options) => { items.forEach((item) => { item.status = 'complete' }); options.onProgress({ total: items.length, completed: items.length, failed: 0, cancelled: 0, active: 0, items }); return { items, completed: items.length, failed: 0, cancelled: 0 } },
    saveState: vi.fn(async () => {}),
    emitState: vi.fn(async () => {})
  })
  const final = await controller.start({ nm: '10', cardUrl: '', resourceUrls: [] })
  expect(resolved).toEqual(['10', '11'])
  expect(final.phase).toBe('complete')
  expect(final.totalVariants).toBe(2)
})
```

```js
// tests/service-worker-contract.test.js
import { expect, it } from 'vitest'
import fs from 'node:fs'

it('imports only local modules and exposes the four bounded message types', () => {
  const source = fs.readFileSync(new URL('../service-worker.js', import.meta.url), 'utf8')
  expect(source).toContain("importScripts(")
  for (const type of ['START_JOB', 'STOP_JOB', 'RETRY_FAILED', 'GET_JOB_STATE']) expect(source).toContain(type)
  expect(source).not.toMatch(/collectParsed|openEditor|uploadMedia|localhost|ozon/i)
})
```

- [ ] **Step 2: Run tests and observe RED**

Run: `cd wb-media-downloader-ext && npm test -- job-controller.test.js service-worker-contract.test.js`

Expected: FAIL because controller and worker do not exist.

- [ ] **Step 3: Implement the injected job controller**

`createJobController(deps)` must keep one active job, reject a second `start` with `任务正在进行`, and update state through one `publish(patch)` helper that merges state, awaits `saveState(state)`, then awaits `emitState(state)`.

`start(payload)` sequence:

1. publish `phase: 'scanning'`;
2. resolve current card using validated hint;
3. compute variant IDs and publish `totalVariants`;
4. for each `nm`, resolve its own card, fetch its own `rich_v1.json` with a missing-rich response treated as empty, build gallery/rich/video arrays, and publish `resolvedVariants/currentVariant`;
5. build one plan and publish `phase: 'downloading', totalFiles`;
6. call the queue and publish every progress snapshot;
7. create a `data:application/json;charset=utf-8,` result URL containing product data plus all item statuses, append it as the final `下载结果.json` download, and publish `phase: 'complete'` or `phase: 'stopped'`.

Any variant-resolution exception must append `{nm,error}` to `variantErrors` and continue. A card with `media.has_video !== true` produces `videos: []` and is not an error. `retryFailed()` copies only failed media items into a new queue while retaining the same batch root. `stop()` aborts the active queue.

`restore(savedState, reconcileDownload)` must handle MV3 Worker recycling. For every persisted item with a `handle`, call `reconcileDownload(handle)` and map Chrome states `complete -> complete`, `interrupted -> failed`, and `in_progress -> downloading`. Pending items are returned to the queue; existing in-progress handles are watched without starting duplicate downloads. Add this test and make it pass:

```js
it('reconciles persisted handles and starts only untouched pending files', async () => {
  const started = []
  const saved = {
    phase: 'downloading', nm: '10',
    items: [
      { id: 'a', handle: 1, status: 'downloading' },
      { id: 'b', handle: 2, status: 'downloading' },
      { id: 'c', handle: 3, status: 'downloading' },
      { id: 'd', status: 'pending' }
    ]
  }
  const controller = Jobs.createJobController({
    now: () => new Date(0),
    runQueue: async (items) => { started.push(...items.map((item) => item.id)); return { items, completed: 0, failed: 0, cancelled: 0 } },
    saveState: async () => {}, emitState: async () => {}
  })
  const state = await controller.restore(saved, async (handle) => ({
    1: { state: 'complete' },
    2: { state: 'interrupted', error: 'NETWORK_FAILED' },
    3: { state: 'in_progress' }
  })[handle])
  expect(state.items.map((item) => item.status)).toEqual(['complete', 'failed', 'downloading', 'pending'])
  expect(started).toEqual(['d'])
})
```

- [ ] **Step 4: Implement the narrow Chrome adapter**

`service-worker.js` must load local UMD modules:

```js
importScripts(
  'common/wb-card.js',
  'common/media-resolver.js',
  'common/file-path.js',
  'common/download-plan.js',
  'common/download-queue.js',
  'common/job-controller.js'
)
```

Adapters:

- `fetchJson(url)`: validate URL using the relevant card/media validator, `fetch(url)`, require `response.ok`, return `response.json()`.
- `probe(url)`: send `GET` with `Range: bytes=0-0`; accept `200` or `206`; abort the response body after headers when supported.
- `start(item)`: call `chrome.downloads.download({url:item.url, filename:item.filename, saveAs:false, conflictAction:'uniquify'})`, then return `{handle: downloadId, completion}` where `completion` resolves/rejects from `chrome.downloads.onChanged` at `complete` or `interrupted`; remove that per-download listener when settled.
- `reconcileDownload(handle)`: call `chrome.downloads.search({id:Number(handle)})` and return the existing Chrome download state and error.
- `saveState`: `chrome.storage.session.set({wbMediaJob: state})`.
- `emitState`: `chrome.tabs.query({url:'https://www.wildberries.ru/catalog/*/detail.aspx*'})` followed by `chrome.tabs.sendMessage(tab.id,{type:'JOB_STATE',state})`; note that `tabs` permission is not needed for querying tabs that match declared host permissions.

The runtime listener must reject messages whose `sender.url` is not a WB product page. It must accept only the four named message types and pass only `nm`, `cardUrl`, and a maximum of 100 filtered WB resource URLs to the controller.

At Worker initialization, read `wbMediaJob` from `chrome.storage.session`. If its phase is `scanning`, `resolving`, or `downloading`, call `controller.restore(savedState, reconcileDownload)` before handling new messages. Register one top-level `chrome.downloads.onChanged` listener so a download event that wakes a recycled Worker triggers reconciliation and queue pumping instead of creating a duplicate file.

- [ ] **Step 5: Run controller, contract, syntax, and manifest checks**

Run:

```powershell
cd wb-media-downloader-ext
npm test -- job-controller.test.js service-worker-contract.test.js
node --check service-worker.js
node -e "JSON.parse(require('fs').readFileSync('manifest.json','utf8')); console.log('manifest ok')"
```

Expected: tests PASS, syntax exits 0, and output contains `manifest ok`.

- [ ] **Step 6: Commit job orchestration**

```bash
git add wb-media-downloader-ext/common/job-controller.js wb-media-downloader-ext/service-worker.js wb-media-downloader-ext/tests/job-controller.test.js wb-media-downloader-ext/tests/service-worker-contract.test.js
git commit -m "feat(wb-download): orchestrate media downloads"
```

### Task 7: Floating panel, progress, stop, retry, and directory actions

**Files:**
- Create: `wb-media-downloader-ext/content/view.js`
- Create: `wb-media-downloader-ext/content/downloader.js`
- Create: `wb-media-downloader-ext/content/downloader.css`
- Create: `wb-media-downloader-ext/tests/view.test.js`
- Create: `wb-media-downloader-ext/tests/content-contract.test.js`

**Interfaces:**
- Produces: `WbMediaView.createPanel(document, handlers) -> {root,render,destroy}`.
- Consumes: `WbMediaCard.nmFromUrl(location.href)` and runtime messages from Task 6.
- Sends: `START_JOB`, `STOP_JOB`, `RETRY_FAILED`, `GET_JOB_STATE`, `OPEN_DOWNLOAD`.

- [ ] **Step 1: Write failing UI-state tests**

```js
// tests/view.test.js
// @vitest-environment jsdom
import { expect, it, vi } from 'vitest'
import View from '../content/view.js'

it('renders idle, running, and completed actions without page text leakage', () => {
  const handlers = { start: vi.fn(), stop: vi.fn(), retry: vi.fn(), open: vi.fn() }
  const panel = View.createPanel(document, handlers)
  panel.render({ phase: 'idle' })
  expect(panel.root.textContent).toContain('下载全部变体素材')
  panel.render({ phase: 'downloading', resolvedVariants: 2, totalVariants: 5, completed: 27, totalFiles: 46, failed: 1, currentVariant: '蓝色' })
  expect(panel.root.textContent).toContain('27 / 46')
  expect(panel.root.textContent).toContain('停止任务')
  panel.render({ phase: 'complete', completed: 44, totalFiles: 46, failed: 2 })
  expect(panel.root.textContent).toContain('重试失败项')
  expect(panel.root.textContent).toContain('打开下载目录')
})
```

```js
// tests/content-contract.test.js
import { expect, it } from 'vitest'
import fs from 'node:fs'

it('collects only bounded card/video resource hints and sends known actions', () => {
  const source = fs.readFileSync(new URL('../content/downloader.js', import.meta.url), 'utf8')
  expect(source).toContain("performance.getEntriesByType('resource')")
  expect(source).toContain('START_JOB')
  expect(source).toContain('GET_JOB_STATE')
  expect(source).not.toMatch(/querySelectorAll\(['\"]img|feedback|recommendation/i)
})
```

- [ ] **Step 2: Run UI tests and observe RED**

Run: `cd wb-media-downloader-ext && npm test -- view.test.js content-contract.test.js`

Expected: FAIL because the content files do not exist.

- [ ] **Step 3: Build the scoped panel DOM and renderer**

`createPanel` must create one root with ID `wb-media-downloader`, a title, status line, detail line, `<progress>`, and action buttons. It must use only `textContent` for remote values. `render` maps states:

- `idle`: primary start button only;
- `scanning|resolving`: discovered/resolved variant counts and stop;
- `downloading`: completed/total, failed, current variant, progress and stop;
- `complete|stopped`: summary, retry when `failed > 0`, open directory, and new run;
- `error`: error text plus new run.

All event listeners call injected handlers; `destroy` removes listeners and the root.

- [ ] **Step 4: Wire page resources and runtime messages**

`content/downloader.js` must:

```js
const nm = WbMediaCard.nmFromUrl(location.href)
if (nm && !document.getElementById('wb-media-downloader')) {
  const resourceUrls = () => performance.getEntriesByType('resource')
    .map((entry) => entry.name)
    .filter((url) => /(?:card\.json|\/mp4\/)/i.test(url) && /(?:wbbasket|geobasket|\.wb\.ru)/i.test(url))
    .slice(-100)
  const cardUrl = () => WbMediaCard.cardJsonUrlFromEntries(resourceUrls(), nm) || ''
  // create panel; START_JOB payload is exactly {nm, cardUrl: cardUrl(), resourceUrls: resourceUrls()}
}
```

On startup send `GET_JOB_STATE`; render the returned state only when `state.nm === nm`. Listen for `JOB_STATE` with the same guard. On History API navigation or `popstate`, destroy the old panel and bootstrap only if the new URL is a product detail page.

Add `OPEN_DOWNLOAD` handling to the worker: use the last completed download ID with `chrome.downloads.show(id)`; if unavailable use `chrome.downloads.showDefaultFolder()`.

- [ ] **Step 5: Add scoped responsive CSS and verify GREEN**

The CSS root must be fixed at `right: 20px; bottom: 20px; z-index: 2147483647`, width `320px`, white background, 12px radius, shadow, and system fonts. Prefix every selector with `#wb-media-downloader`. At viewport widths below 480px use `left: 12px; right: 12px; width: auto`.

Run:

```powershell
cd wb-media-downloader-ext
npm test -- view.test.js content-contract.test.js
node --check content/view.js
node --check content/downloader.js
```

Expected: tests PASS and both syntax checks exit 0.

- [ ] **Step 6: Commit the on-page experience**

```bash
git add wb-media-downloader-ext/content/view.js wb-media-downloader-ext/content/downloader.js wb-media-downloader-ext/content/downloader.css wb-media-downloader-ext/service-worker.js wb-media-downloader-ext/tests/view.test.js wb-media-downloader-ext/tests/content-contract.test.js
git commit -m "feat(wb-download): add floating progress panel"
```

### Task 8: Documentation, full verification, and real WB acceptance

**Files:**
- Create: `wb-media-downloader-ext/README.md`
- Modify only if verification finds a failing requirement: files under `wb-media-downloader-ext/`

**Interfaces:**
- Produces: user installation and troubleshooting instructions.
- Verifies: all spec acceptance criteria on a live multi-variant WB page.

- [ ] **Step 1: Write README acceptance content before final verification**

README must contain these exact sections with concrete instructions:

```markdown
# WB 图片视频下载器

## 安装
1. 在本目录运行 `npm install`（仅用于测试；插件运行不需要 Node.js）。
2. 打开 `chrome://extensions`，启用“开发者模式”。
3. 点击“加载已解压的扩展程序”，选择本目录。

## 使用
打开 `https://www.wildberries.ru/catalog/<商品ID>/detail.aspx`，点击右下角“下载全部变体素材”。

## 保存位置
`下载/WB下载/<商品标题>_imt-<商品组ID>/<时间批次>/<变体>/轮播图|详情图|视频/`

## 权限
- `downloads`：创建、监控和取消用户主动发起的媒体下载。
- `storage`：临时保存当前下载任务进度。
- WB 域名权限：读取商品卡、卖家详情图和商品视频。

## 故障排查
- “card.json 不可用”：刷新商品页后重试，并确认 WB 页面本身能正常显示商品。
- 个别变体失败：任务完成后点击“重试失败项”。
- 没有视频：该变体未声明商品视频，不属于失败。
```

- [ ] **Step 2: Run the complete automated verification stack**

Run:

```powershell
cd wb-media-downloader-ext
npm test
Get-ChildItem -Recurse -Filter '*.js' | Where-Object { $_.FullName -notmatch '\\node_modules\\' } | ForEach-Object { node --check $_.FullName; if ($LASTEXITCODE -ne 0) { throw "syntax failed: $($_.FullName)" } }
node -e "const m=JSON.parse(require('fs').readFileSync('manifest.json','utf8')); if(m.permissions.includes('tabs')||JSON.stringify(m).includes('<all_urls>')) process.exit(1); console.log('manifest boundary ok')"
```

Expected: all Vitest files PASS, every syntax check exits 0, and output ends with `manifest boundary ok`.

- [ ] **Step 3: Load the unpacked extension and verify a live multi-variant product**

Use a currently available multi-variant product discovered from WB itself. The known July 2026 example `1190575806` had sibling IDs `399656234`, `737964991`, `452506837`, `1190575807`, and `1190575806`; re-check live card data rather than assuming it remains active.

Acceptance checklist:

- panel appears only on `/catalog/<nm>/detail.aspx`;
- one click discovers every currently resolvable sibling;
- each sibling folder contains its own ordered gallery;
- `rich_v1.json` content images land only in `详情图`;
- review photos visible lower on the page are absent;
- video paths contain the owning `nm_id`, play successfully, and are never copied from another sibling;
- stop leaves completed files intact;
- one forced bad media URL appears as failed and succeeds or remains explicitly recorded after retry;
- `下载结果.json` paths and counts match the actual batch;
- “打开下载目录” reveals a file in the correct batch.

- [ ] **Step 4: Inspect unrelated workspace state and commit only the plugin docs/fixes**

Run: `git status --short` and verify no pre-existing non-plugin changes are staged.

```bash
git add wb-media-downloader-ext/README.md wb-media-downloader-ext
git commit -m "docs(wb-download): document install and verification"
```

Before committing, use `git diff --cached --name-only` and abort the commit if any path is outside `wb-media-downloader-ext/`.

- [ ] **Step 5: Final evidence capture**

Record in the handoff:

- exact `npm test` pass count;
- exact syntax/manifest commands run;
- live WB product `nm_id` and discovered sibling count;
- successful gallery/rich/video file counts by variant;
- any WB-side unavailable media explicitly listed as unavailable rather than silently substituted.
