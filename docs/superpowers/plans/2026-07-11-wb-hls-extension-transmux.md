# WB HLS Extension Transmux Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert WB VOD HLS MPEG-TS playlists to high-resolution MP4 inside the extension and upload the result to OSS as the draft's final `video_url`.

**Architecture:** A focused UMD module parses and downloads HLS media playlists, then calls a locally vendored mux.js runtime to transmux ordered TS bytes into fragmented MP4. The background service worker exposes this conversion through the existing message bridge and uploads the prepared MP4 Blob with the existing OSS presign flow; collect-flow invokes it only when WB provides HLS without direct MP4.

**Tech Stack:** Chromium MV3 service worker, JavaScript UMD modules, mux.js 6.3.0, Fetch/Blob APIs, Vitest 2.1.8, existing OSS presign API.

## Global Constraints

- Preserve the HLS source resolution and encoded quality; do not decode or re-encode video.
- Never fall back to the WB 360p direct MP4.
- Support unencrypted VOD media playlists containing MPEG-TS segments only.
- Reject playlists with more than 300 segments or more than 512 MiB of downloaded segment data.
- A failed segment aborts conversion; partial MP4 data must never be uploaded.
- Keep `source_raw.video_hls_url` when conversion fails and leave `video_url` empty.
- All executable extension code must be local; pin mux.js to exactly 6.3.0 and vendor its browser runtime.

---

## File Structure

- Create `ozon-seller-helper-ext/common/hls-transmux.js`: playlist parsing, ordered segment download, byte limits, and mux.js adapter.
- Create `ozon-seller-helper-ext/tests/hls-transmux.test.js`: unit tests for HLS parsing, downloading, limits, and MP4 assembly.
- Create `ozon-seller-helper-ext/vendor/mux.js`: pinned browser runtime copied from mux.js 6.3.0.
- Modify `ozon-seller-helper-ext/package.json` and `package-lock.json`: pin mux.js dependency.
- Modify `ozon-seller-helper-ext/background.js`: load the runtime/module, upload a prepared MP4 Blob, and expose one bridge operation.
- Create `ozon-seller-helper-ext/common/hls-upload.js`: compose conversion with prepared-Blob OSS upload behind a testable UMD API.
- Modify `ozon-seller-helper-ext/common/collect-flow.js`: invoke HLS conversion for WB HLS-only data and write the OSS URL to `video_url`.
- Modify `ozon-seller-helper-ext/tests/collect-flow-wb.test.js`: integration coverage for success and failure behavior.
- Create `ozon-seller-helper-ext/tests/hls-upload.test.js`: focused conversion/upload composition coverage without loading the Chrome worker.

### Task 1: HLS Playlist to MP4 Module

**Files:**
- Create: `ozon-seller-helper-ext/common/hls-transmux.js`
- Create: `ozon-seller-helper-ext/tests/hls-transmux.test.js`
- Create: `ozon-seller-helper-ext/vendor/mux.js`
- Modify: `ozon-seller-helper-ext/package.json`
- Modify: `ozon-seller-helper-ext/package-lock.json`

**Interfaces:**
- Consumes: `fetchImpl(url) -> Response`, `createTransmuxer() -> mux.js Transmuxer`.
- Produces: `parseMediaPlaylist(text, playlistUrl) -> string[]` and `transmuxHlsToMp4(playlistUrl, { fetchImpl, createTransmuxer, maxSegments, maxBytes }) -> Promise<Blob>`.

- [ ] **Step 1: Write failing playlist and conversion tests**

Create tests that import the wished-for API and exercise real Blob/Response objects. Use a small fake transmuxer only at the external mux.js boundary:

```js
const { parseMediaPlaylist, transmuxHlsToMp4 } = require('../common/hls-transmux')

it('resolves VOD TS segments in manifest order', () => {
  const text = '#EXTM3U\n#EXT-X-PLAYLIST-TYPE:VOD\n#EXTINF:1,\n1.ts\n#EXTINF:1,\n../2.ts?x=1\n#EXT-X-ENDLIST\n'
  expect(parseMediaPlaylist(text, 'https://cdn.example/a/1440p/index.m3u8')).toEqual([
    'https://cdn.example/a/1440p/1.ts',
    'https://cdn.example/a/2.ts?x=1'
  ])
})

it('downloads ordered TS segments and returns video/mp4', async () => {
  const seen = []
  const fetchImpl = async (url) => {
    seen.push(url)
    if (url.endsWith('.m3u8')) return new Response('#EXTM3U\n#EXT-X-PLAYLIST-TYPE:VOD\n#EXTINF:1,\n1.ts\n#EXTINF:1,\n2.ts\n#EXT-X-ENDLIST')
    return new Response(new Uint8Array([url.includes('1.ts') ? 1 : 2]))
  }
  const listeners = {}
  const createTransmuxer = () => ({
    on: (name, fn) => { listeners[name] = fn },
    push: (bytes) => { expect(Array.from(bytes)).toEqual([1, 2]) },
    flush: () => listeners.data({ initSegment: new Uint8Array([9]), data: new Uint8Array([8]) })
  })
  const blob = await transmuxHlsToMp4('https://cdn.example/v/index.m3u8', { fetchImpl, createTransmuxer })
  expect(blob.type).toBe('video/mp4')
  expect(Array.from(new Uint8Array(await blob.arrayBuffer()))).toEqual([9, 8])
  expect(seen.slice(1)).toEqual(['https://cdn.example/v/1.ts', 'https://cdn.example/v/2.ts'])
})
```

Add separate tests asserting rejection of a master playlist, missing
`#EXT-X-ENDLIST`, non-TS segments, 301 segments, a failed segment response, and
total bytes above an injected `maxBytes: 1`.

- [ ] **Step 2: Run the module tests and verify RED**

Run: `npm.cmd test -- hls-transmux.test.js`

Expected: FAIL because `../common/hls-transmux` does not exist.

- [ ] **Step 3: Pin and vendor mux.js**

Run from `ozon-seller-helper-ext/`:

```powershell
npm.cmd install --save-exact mux.js@6.3.0
New-Item -ItemType Directory -Force vendor | Out-Null
Copy-Item node_modules/mux.js/dist/mux.js vendor/mux.js
```

Verify `package.json` contains `"mux.js": "6.3.0"` under `dependencies`, and
`vendor/mux.js` is the distributable UMD build rather than source modules.

- [ ] **Step 4: Implement the minimal HLS module**

Implement a UMD export. `parseMediaPlaylist` must validate VOD/end marker,
reject `#EXT-X-STREAM-INF`, encryption, byte ranges, and non-`.ts` segment paths,
then resolve each segment with `new URL(line, playlistUrl).href`.

`transmuxHlsToMp4` must fetch the playlist, fetch segments sequentially in
manifest order, accumulate their `Uint8Array` values while enforcing count and
byte limits, concatenate TS bytes once, and pass them to one transmuxer. Register
`data` and `error` handlers before `push()`/`flush()`. Build the Blob from the
first emitted `initSegment` plus every emitted `data` chunk:

```js
const chunks = []
let wroteInit = false
transmuxer.on('data', (segment) => {
  if (!wroteInit) {
    chunks.push(segment.initSegment)
    wroteInit = true
  }
  chunks.push(segment.data)
})
transmuxer.push(joinedTs)
transmuxer.flush()
if (!wroteInit || chunks.length < 2) throw new Error('HLS transmux produced no MP4 data')
return new Blob(chunks, { type: 'video/mp4' })
```

Default `createTransmuxer` to `() => new root.muxjs.mp4.Transmuxer({ keepOriginalTimestamps: true })`.

- [ ] **Step 5: Run module tests and verify GREEN**

Run: `npm.cmd test -- hls-transmux.test.js`

Expected: all `hls-transmux.test.js` tests PASS.

- [ ] **Step 6: Commit Task 1**

```powershell
git add ozon-seller-helper-ext/package.json ozon-seller-helper-ext/package-lock.json ozon-seller-helper-ext/vendor/mux.js ozon-seller-helper-ext/common/hls-transmux.js ozon-seller-helper-ext/tests/hls-transmux.test.js
git commit -m "feat(ext): transmux WB HLS video to MP4"
```

### Task 2: Prepared MP4 OSS Upload in Background Worker

**Files:**
- Modify: `ozon-seller-helper-ext/background.js`
- Create: `ozon-seller-helper-ext/common/hls-upload.js`
- Create: `ozon-seller-helper-ext/tests/hls-upload.test.js`

**Interfaces:**
- Consumes: `OzonHelperHls.transmuxHlsToMp4(url, dependencies) -> Promise<Blob>` and existing OSS presign response `{results: [{key, upload_url, url}]}`.
- Produces: `OzonHelperHlsUpload.uploadHlsVideoOss(playlistUrl, dependencies) -> Promise<{url: string, source_url: string}>`; message type `uploadHlsVideoOss` returns that result through the existing bridge response envelope.

- [ ] **Step 1: Write the failing background helper tests**

Create a UMD composition module and test it with injected conversion and upload dependencies:

```js
it('uploads the converted blob as video/mp4 with an mp4 key', async () => {
  const blob = new Blob([new Uint8Array([1, 2])], { type: 'video/mp4' })
  const calls = []
  const result = await uploadHlsVideoOss('https://wb/video/index.m3u8', {
    transmux: async () => blob,
    uploadPrepared: async (item) => {
      calls.push(item)
      return 'https://oss.example/ozon-media/hash.mp4'
    }
  })
  expect(calls[0].contentType).toBe('video/mp4')
  expect(calls[0].extension).toBe('mp4')
  expect(calls[0].blob).toBe(blob)
  expect(result.url).toBe('https://oss.example/ozon-media/hash.mp4')
})
```

Add a test that conversion rejection prevents `uploadPrepared` from being
called and preserves the original error.

- [ ] **Step 2: Run the background tests and verify RED**

Run: `npm.cmd test -- hls-upload.test.js`

Expected: FAIL because `../common/hls-upload` does not exist.

- [ ] **Step 3: Implement prepared-Blob upload and message routing**

Implement `common/hls-upload.js` as a UMD module with the tested function, then
load local scripts in dependency order:

```js
importScripts('/common/bridge.js', '/common/media-upload.js', '/vendor/mux.js', '/common/hls-transmux.js', '/common/hls-upload.js', '/common/wb.js')
```

Extract the presign/PUT portion of `uploadMediaOss` into an internal
`uploadPreparedOss({ sourceUrl, blob, contentType, extension })` helper. Compute
the existing SHA-256 key as `ozon-media/<hash>.<extension>`, send the exact MIME
to `/api/media/presign`, PUT the Blob, and return the public URL. Keep normal
image/direct-MP4 behavior using this helper without changing its returned map.

Implement:

```js
async function uploadHlsVideoOss(playlistUrl, deps) {
  const transmux = deps.transmux
  const uploadPrepared = deps.uploadPrepared
  const blob = await transmux(playlistUrl)
  const url = await uploadPrepared({
    sourceUrl: playlistUrl, blob, contentType: 'video/mp4', extension: 'mp4'
  })
  return { source_url: playlistUrl, url }
}
```

In the background message branch call
`self.OzonHelperHlsUpload.uploadHlsVideoOss(playlistUrl, { transmux:
self.OzonHelperHls.transmuxHlsToMp4, uploadPrepared: uploadPreparedOss })`,
matching the existing asynchronous response pattern used by `uploadMediaOss`.

- [ ] **Step 4: Run focused uploader tests and existing media tests**

Run: `npm.cmd test -- hls-upload.test.js media-upload.test.js`

Expected: both files PASS.

- [ ] **Step 5: Commit Task 2**

```powershell
git add ozon-seller-helper-ext/background.js ozon-seller-helper-ext/common/hls-upload.js ozon-seller-helper-ext/tests/hls-upload.test.js
git commit -m "feat(ext): upload transmuxed HLS video to OSS"
```

### Task 3: WB Collection Integration and End-to-End Verification

**Files:**
- Modify: `ozon-seller-helper-ext/common/collect-flow.js`
- Modify: `ozon-seller-helper-ext/tests/collect-flow-wb.test.js`

**Interfaces:**
- Consumes: `data.source_raw.video_hls_url`, bridge operation `uploadHlsVideoOss`.
- Produces: `data.video_url` containing the uploaded OSS MP4 URL before `collectParsed` is sent to the backend.

- [ ] **Step 1: Write failing WB collection integration tests**

Extend the existing WB fixture setup with HLS-only parsed data. Stub
`OzonHelperBridge.bgCall` so `uploadHlsVideoOss` returns an OSS URL and assert
the subsequent `collectParsed` payload contains it:

```js
expect(calls).toContainEqual([
  'uploadHlsVideoOss',
  { url: 'https://wb.example/hls/1440p/index.m3u8' }
])
expect(collected[0].data.video_url).toBe('https://oss.example/video.mp4')
expect(collected[0].data.source_raw.video_hls_url).toBe('https://wb.example/hls/1440p/index.m3u8')
```

Add a failure test where the bridge returns `{ok: false, error: 'segment 4 download failed'}`. Assert collection still completes, `video_url` remains empty,
`video_hls_url` remains present, and the status callback receives a video
conversion failure message. Retain the existing direct-MP4 test to prove it
does not call `uploadHlsVideoOss`.

- [ ] **Step 2: Run WB collection tests and verify RED**

Run: `npm.cmd test -- collect-flow-wb.test.js`

Expected: FAIL because the collection flow does not call `uploadHlsVideoOss` and
the collected payload has an empty `video_url`.

- [ ] **Step 3: Implement HLS-only collection handling**

Before normal `_rehostMedia`, add a focused helper:

```js
async function _prepareHlsVideo(data, onStatus) {
  const hls = data && data.source_raw && data.source_raw.video_hls_url
  if (!hls || data.video_url) return data
  if (onStatus) onStatus('正在转换高清视频...', true)
  const r = await OzonHelperBridge.bgCall('uploadHlsVideoOss', { url: hls })
  if (r && r.ok && r.data && r.data.url) {
    data.video_url = r.data.url
    return data
  }
  if (onStatus) onStatus('高清视频转换失败，草稿将不含视频', false)
  return data
}
```

Call `await _prepareHlsVideo(data, onStatus)` for parsed WB data immediately
before `collectParsed`. The current WB flow creates the draft first and invokes
`rehostPending` afterward for remaining source images; the generated MP4 is
already this application's OSS URL, so the pending-media filter skips it by the
existing backend-base prefix rule.

- [ ] **Step 4: Run WB parser and collection tests**

Run: `npm.cmd test -- wb.test.js collect-flow-wb.test.js hls-transmux.test.js hls-upload.test.js`

Expected: all targeted tests PASS.

- [ ] **Step 5: Run the complete extension suite**

Run from `ozon-seller-helper-ext/`: `npm.cmd test`

Expected: all test files PASS with no unhandled rejections.

- [ ] **Step 6: Inspect extension package inputs**

Run:

```powershell
Test-Path vendor/mux.js
rg -n "vendor/mux.js|common/hls-transmux.js|uploadHlsVideoOss" background.js common tests
git diff --check
```

Expected: `Test-Path` prints `True`; background imports both local runtimes;
bridge and tests reference `uploadHlsVideoOss`; `git diff --check` exits 0.

- [ ] **Step 7: Commit Task 3**

```powershell
git add ozon-seller-helper-ext/common/collect-flow.js ozon-seller-helper-ext/tests/collect-flow-wb.test.js
git commit -m "fix(ext): attach high-resolution WB video to drafts"
```

- [ ] **Step 8: Manual browser verification**

Reload the unpacked extension, open the verified WB product, start collection,
and confirm the status progresses through video conversion and upload. Open the
created draft and verify `video_url` ends in `.mp4`, the preview plays, and the
video dimensions report the high-resolution source rather than 360p. If browser
state is unavailable, report this manual check as outstanding without weakening
the automated verification result.
