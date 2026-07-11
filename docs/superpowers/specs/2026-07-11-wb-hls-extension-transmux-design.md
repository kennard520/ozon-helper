# WB HLS Extension Transmux Design

## Goal

When a Wildberries product exposes only a high-resolution HLS playlist, the
extension must produce a publishable MP4 and upload it through the existing OSS
media flow. It must preserve the source resolution and must not silently fall
back to the low-resolution 360p MP4.

## Current Behavior and Root Cause

The WB parser detects the highest loaded HLS playlist and stores it as
`source_raw.video_hls_url`. The draft's `video_url` remains empty because an
`.m3u8` playlist is not a single publishable video file. Existing media upload
code only processes `video_url`, so the HLS source never reaches the upload
pipeline and the final draft has no video.

The verified sample playlist is a VOD manifest containing ordered MPEG-TS
segments. Equivalent 720p, 1080p, and 1440p direct MP4 paths return 404; only a
360p direct MP4 exists.

## Architecture

The extension background service worker will own HLS acquisition and
transmuxing because it already has cross-origin host permissions and performs
OSS uploads.

Add a focused HLS module with one public operation:

```text
transmuxHlsToMp4(playlistUrl, dependencies) -> Blob
```

The operation will:

1. Fetch and parse the media playlist.
2. Resolve segment references relative to the playlist URL.
3. Download every segment in manifest order.
4. Feed the MPEG-TS bytes to a vendored browser-compatible transmux library.
5. Assemble one fragmented MP4 Blob with MIME type `video/mp4`.

The operation performs container transmuxing only. It does not decode or
re-encode video, so the source resolution and encoded quality are retained.

The existing OSS uploader will accept an optional prepared media item containing
the source URL, Blob, MIME type, and forced `.mp4` extension. This avoids fetching
the `.m3u8` as if it were a normal file. On successful upload, the HLS playlist
URL maps to the resulting OSS MP4 URL and normal media-map application writes it
to `data.video_url` before the draft is sent to the backend.

## Data Flow

For WB data with an empty `video_url` and a non-empty
`source_raw.video_hls_url`:

```text
WB parser
  -> collect flow detects HLS-only video
  -> background fetches playlist and TS segments
  -> transmuxer produces video/mp4 Blob
  -> existing presign and OSS PUT flow uploads Blob as .mp4
  -> collect flow sets data.video_url to OSS URL
  -> backend creates or refreshes draft with a final video URL
```

Direct MP4 sources continue through the current path unchanged.

## Failure Handling

- Reject non-VOD or malformed playlists with a concise conversion error.
- Treat a missing or failed segment as a failed conversion; never upload a
  partial MP4.
- Preserve `source_raw.video_hls_url` and leave `video_url` empty on failure.
- Report video conversion failure through the existing collection status
  callback while allowing images and product data to complete.
- Do not fall back to the known 360p MP4 because that recreates the original
  low-resolution defect.
- Apply practical limits for segment count and total downloaded bytes to avoid
  exhausting extension memory.

## Packaging

Use a browser-compatible MPEG-TS to fragmented-MP4 transmux library and vendor
its distributable runtime inside the extension. The MV3 service worker will load
that local file with `importScripts`; no remote executable code is introduced.
The package dependency and vendored artifact version must be pinned and covered
by the extension packaging process.

## Tests

Tests will be written before production changes and will cover:

- Relative segment URLs are resolved and fetched in manifest order.
- A valid VOD playlist produces a `video/mp4` Blob.
- The prepared Blob is uploaded with an `.mp4` object key and MIME type.
- The resulting OSS URL is assigned to `data.video_url` for HLS-only WB data.
- Direct MP4 collection remains unchanged.
- Malformed manifests, failed segments, and excessive size/count limits fail
  without producing or uploading a partial video.
- The complete extension Vitest suite passes after integration.

## Non-Goals

- Video transcoding, resizing, bitrate changes, or quality enhancement.
- Support for encrypted, live, or adaptive master playlists in this iteration.
- Server-side ffmpeg installation or conversion.
- Automatic fallback to low-resolution WB MP4 assets.
