# CNLinko Catalog Collector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run a resumable local collector that inventories CNLinko's Chinese catalog, enriches matched models with English text, downloads product images and public documents, and exports Ozon-preparation indexes.

**Architecture:** Add an isolated uv workspace application under `apps/cnlinko_collector`. Separate HTTP transport, HTML/JSON parsing, persistence/downloads, orchestration, and exports so fixtures can test every boundary without hitting the live site. Use the Chinese site as authoritative, match English records by normalized model, and persist progress in SQLite plus per-model JSON before producing CSV/XLSX reports.

**Tech Stack:** Python 3.10+, httpx, BeautifulSoup4, openpyxl, SQLite, pytest, uv

## Global Constraints

- Default output is `data/cnlinko_catalog/`, and generated catalog data must remain outside Git.
- Chinese data is authoritative; English data only enriches matching normalized models.
- Download all public product originals and PDF/DWG/STEP/other product attachments; do not bypass login, CAPTCHA, payment, or access controls.
- Use conservative concurrency, request spacing, timeout, retry/backoff, resumability, SHA-256 deduplication, and atomic file replacement.
- Preserve original values and URLs even when normalized values or safe Windows filenames are used locally.

---

### Task 1: Package, domain models, and normalization

**Files:**
- Create: `apps/cnlinko_collector/pyproject.toml`
- Create: `apps/cnlinko_collector/src/cnlinko_collector/__init__.py`
- Create: `apps/cnlinko_collector/src/cnlinko_collector/models.py`
- Create: `apps/cnlinko_collector/src/cnlinko_collector/normalize.py`
- Create: `apps/cnlinko_collector/tests/test_normalize.py`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `normalize_model(value: str) -> str`, `safe_filename(value: str) -> str`, and dataclasses `Asset`, `ProductRecord`, `CrawlFailure`.

- [ ] **Step 1: Write failing normalization tests**

```python
from cnlinko_collector.normalize import normalize_model, safe_filename


def test_normalize_model_unifies_case_spaces_and_dashes():
    assert normalize_model(" lp－12 c02pe  ") == "LP-12-C02PE"


def test_safe_filename_removes_windows_reserved_characters():
    assert safe_filename('LP12:2芯/公插头*?') == "LP12_2芯_公插头__"
```

- [ ] **Step 2: Run the tests and verify the import failure**

Run: `python -m uv run pytest apps/cnlinko_collector/tests/test_normalize.py -q`

Expected: FAIL because `cnlinko_collector` does not exist.

- [ ] **Step 3: Add package metadata, models, normalization, and ignore rule**

`pyproject.toml` must declare the `cnlinko-collect` console script and dependencies `httpx>=0.27`, `beautifulsoup4>=4.12`, and `openpyxl>=3.1`. `ProductRecord` must contain source language/URL, category path, Chinese and English names/descriptions, raw and normalized model, parameters, features, images, and documents. `Asset` must contain kind, URL, original name, local path, media type, byte count, and SHA-256. Add `/data/cnlinko_catalog/` to `.gitignore`.

- [ ] **Step 4: Run focused tests**

Run: `python -m uv run pytest apps/cnlinko_collector/tests/test_normalize.py -q`

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add .gitignore apps/cnlinko_collector
git commit -m "feat(collector): scaffold cnlinko catalog models"
```

### Task 2: Transport, throttling, and resumable crawl state

**Files:**
- Create: `apps/cnlinko_collector/src/cnlinko_collector/http.py`
- Create: `apps/cnlinko_collector/src/cnlinko_collector/state.py`
- Create: `apps/cnlinko_collector/tests/test_http.py`
- Create: `apps/cnlinko_collector/tests/test_state.py`

**Interfaces:**
- Consumes: `CrawlFailure` from Task 1.
- Produces: `SiteClient.get(url)`, `SiteClient.post(url, data)`, and `CrawlState` methods `mark_page`, `page_status`, `record_asset`, `asset_by_hash`, `record_failure`, `summary`.

- [ ] **Step 1: Write failing tests for retry and persisted state**

```python
def test_client_retries_503_then_returns_response(fake_transport):
    client = SiteClient(transport=fake_transport([503, 200]), min_interval=0)
    assert client.get("https://example.test/item").status_code == 200
    assert fake_transport.calls == 2


def test_state_survives_reopen(tmp_path):
    path = tmp_path / "state.sqlite3"
    CrawlState(path).mark_page("https://example.test/p", "done", "abc")
    assert CrawlState(path).page_status("https://example.test/p") == "done"
```

- [ ] **Step 2: Verify failures**

Run: `python -m uv run pytest apps/cnlinko_collector/tests/test_http.py apps/cnlinko_collector/tests/test_state.py -q`

Expected: FAIL because transport and state modules do not exist.

- [ ] **Step 3: Implement transport and SQLite state**

Implement a descriptive User-Agent, default 30-second timeout, configurable minimum 0.5-second request interval, and retries for network errors plus HTTP 429/500/502/503/504 using delays `1, 2, 4, 8` seconds. SQLite tables must track pages, assets, asset-to-model relations, failures, timestamps, status, content hashes, and error text. All SQL writes use transactions and unique URL/hash constraints.

- [ ] **Step 4: Run focused tests**

Run: `python -m uv run pytest apps/cnlinko_collector/tests/test_http.py apps/cnlinko_collector/tests/test_state.py -q`

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/cnlinko_collector
git commit -m "feat(collector): add resilient transport and crawl state"
```

### Task 3: Chinese list, detail, download-center, and English parsers

**Files:**
- Create: `apps/cnlinko_collector/src/cnlinko_collector/parsers.py`
- Create: `apps/cnlinko_collector/tests/fixtures/cn_list.json`
- Create: `apps/cnlinko_collector/tests/fixtures/cn_detail.html`
- Create: `apps/cnlinko_collector/tests/fixtures/download.html`
- Create: `apps/cnlinko_collector/tests/fixtures/en_detail.html`
- Create: `apps/cnlinko_collector/tests/test_parsers.py`

**Interfaces:**
- Consumes: `ProductRecord`, `Asset`, `normalize_model`.
- Produces: `parse_list_response(payload, base_url) -> tuple[list[str], int]`, `parse_product_page(html, url, language) -> list[ProductRecord]`, and `parse_download_page(html, base_url) -> list[tuple[str, Asset]]`.

- [ ] **Step 1: Capture sanitized fixtures**

Save the smallest live-response fragments that retain one pagination result, one multi-model product, parameters, image URLs, and PDF/DWG/STEP links. Remove analytics scripts, contact data, and unrelated navigation.

- [ ] **Step 2: Write failing parser tests**

```python
def test_cn_detail_keeps_models_parameters_and_original_images(load_fixture):
    records = parse_product_page(load_fixture("cn_detail.html"), "https://www.cnlinko.cn/p/1.html", "zh-CN")
    assert records[0].normalized_model == "LP-12-C02PE-02-001"
    assert records[0].parameters["额定电流"]
    assert any(asset.kind == "image" for asset in records[0].images)


def test_download_page_maps_three_formats_to_model(load_fixture):
    rows = parse_download_page(load_fixture("download.html"), "https://www.cnlinko.cn")
    assert {asset.kind for _, asset in rows} == {"pdf", "dwg", "step"}
```

- [ ] **Step 3: Verify failures**

Run: `python -m uv run pytest apps/cnlinko_collector/tests/test_parsers.py -q`

Expected: FAIL because parser functions do not exist.

- [ ] **Step 4: Implement tolerant parsers**

Parse structured labels rather than fixed child indexes; resolve relative and protocol-relative URLs; prefer original/lazy-load image attributes over thumbnails; preserve unknown parameter labels; emit multiple records when one page exposes multiple models; and return empty optional fields instead of dropping an otherwise valid model.

- [ ] **Step 5: Run tests and commit**

Run: `python -m uv run pytest apps/cnlinko_collector/tests/test_parsers.py -q`

Expected: all tests PASS.

```bash
git add apps/cnlinko_collector
git commit -m "feat(collector): parse cnlinko catalog and downloads"
```

### Task 4: Atomic asset store and SHA-256 deduplication

**Files:**
- Create: `apps/cnlinko_collector/src/cnlinko_collector/assets.py`
- Create: `apps/cnlinko_collector/tests/test_assets.py`

**Interfaces:**
- Consumes: `SiteClient`, `CrawlState`, `Asset`, `safe_filename`.
- Produces: `AssetStore.fetch(asset: Asset, normalized_model: str) -> Asset`.

- [ ] **Step 1: Write failing asset tests**

```python
def test_fetch_is_atomic_and_deduplicates_equal_content(tmp_path, fake_client):
    store = AssetStore(tmp_path, CrawlState(tmp_path / "state.db"), fake_client(b"%PDF-1.7\nbody"))
    first = store.fetch(Asset(kind="pdf", url="https://x/a.pdf"), "LP-12-A")
    second = store.fetch(Asset(kind="pdf", url="https://x/b.pdf"), "LP-12-B")
    assert first.sha256 == second.sha256
    assert not list(tmp_path.rglob("*.part"))
    assert len(list((tmp_path / "objects").iterdir())) == 1
```

- [ ] **Step 2: Verify failure**

Run: `python -m uv run pytest apps/cnlinko_collector/tests/test_assets.py -q`

Expected: FAIL because `AssetStore` does not exist.

- [ ] **Step 3: Implement content-addressed storage**

Stream responses into `.part` files while hashing, reject HTML bodies for document assets, require non-empty content, validate `%PDF-` for PDF, store one canonical object per SHA-256, then create per-model hard links with copy fallback. Atomically rename completed files and record every model relationship even for duplicate content.

- [ ] **Step 4: Run tests and commit**

Run: `python -m uv run pytest apps/cnlinko_collector/tests/test_assets.py -q`

Expected: all tests PASS.

```bash
git add apps/cnlinko_collector
git commit -m "feat(collector): download and deduplicate catalog assets"
```

### Task 5: Orchestrator, bilingual merge, CLI, and structured output

**Files:**
- Create: `apps/cnlinko_collector/src/cnlinko_collector/collector.py`
- Create: `apps/cnlinko_collector/src/cnlinko_collector/cli.py`
- Create: `apps/cnlinko_collector/tests/test_collector.py`
- Create: `apps/cnlinko_collector/tests/test_cli.py`

**Interfaces:**
- Consumes: Tasks 1-4 public interfaces.
- Produces: `CatalogCollector.discover()`, `collect_metadata()`, `collect_assets()`, `write_model_json()`, `run()`, and console command `cnlinko-collect`.

- [ ] **Step 1: Write failing orchestration tests**

```python
def test_merge_keeps_chinese_truth_and_adds_english_text():
    merged, differences = merge_records(cn_record(voltage="250V"), en_record(voltage="300V"))
    assert merged.parameters["额定电压"] == "250V"
    assert merged.name_en
    assert differences[0].field == "额定电压"


def test_resume_skips_done_page(tmp_path, scripted_client):
    collector = make_collector(tmp_path, scripted_client)
    collector.run(metadata_only=True)
    calls = scripted_client.calls
    collector.run(metadata_only=True)
    assert scripted_client.calls == calls
```

- [ ] **Step 2: Verify failures**

Run: `python -m uv run pytest apps/cnlinko_collector/tests/test_collector.py apps/cnlinko_collector/tests/test_cli.py -q`

Expected: FAIL because orchestration and CLI modules do not exist.

- [ ] **Step 3: Implement staged collection**

Discover category/list pagination from both site navigation and public search endpoints, collect Chinese records, join download-center assets by normalized model, query/match English pages only for known Chinese models, write deterministic UTF-8 `product.json`, then download assets. CLI options must include `--output`, `--metadata-only`, `--assets-only`, `--retry-failures`, `--min-interval`, `--max-pages`, and `--log-level`.

- [ ] **Step 4: Run tests and commit**

Run: `python -m uv run pytest apps/cnlinko_collector/tests/test_collector.py apps/cnlinko_collector/tests/test_cli.py -q`

Expected: all tests PASS.

```bash
git add apps/cnlinko_collector
git commit -m "feat(collector): orchestrate resumable bilingual collection"
```

### Task 6: CSV/XLSX exports and audit reports

**Files:**
- Create: `apps/cnlinko_collector/src/cnlinko_collector/export.py`
- Create: `apps/cnlinko_collector/tests/test_export.py`

**Interfaces:**
- Consumes: collected `ProductRecord` values and `CrawlState.summary()`.
- Produces: `export_catalog(records, output_dir)`, `export_reports(state, differences, output_dir)`, and `write_manifest(state, output_dir)`.

- [ ] **Step 1: Write failing export test**

```python
def test_exports_catalog_and_reports(tmp_path, sample_records):
    export_catalog(sample_records, tmp_path)
    assert (tmp_path / "catalog.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    book = openpyxl.load_workbook(tmp_path / "catalog.xlsx", read_only=True)
    assert {"产品", "参数", "图片", "资料"}.issubset(book.sheetnames)
```

- [ ] **Step 2: Verify failure**

Run: `python -m uv run pytest apps/cnlinko_collector/tests/test_export.py -q`

Expected: FAIL because export functions do not exist.

- [ ] **Step 3: Implement exports**

Write UTF-8-BOM CSV and an XLSX workbook with frozen headers, filters, readable widths, hyperlink source/local paths, and sheets `产品`, `参数`, `图片`, `资料`. Write `reports/failures.csv`, `reports/missing_files.csv`, `reports/cn_en_differences.csv`, and `manifest.json` with timestamps and product/model/image/document/deduplicated/failed counts.

- [ ] **Step 4: Run tests and commit**

Run: `python -m uv run pytest apps/cnlinko_collector/tests/test_export.py -q`

Expected: all tests PASS.

```bash
git add apps/cnlinko_collector
git commit -m "feat(collector): export catalog indexes and audit reports"
```

### Task 7: Live smoke probe, full collection, and final verification

**Files:**
- Create: `apps/cnlinko_collector/tests/smoke_cnlinko_live.py`
- Create: `apps/cnlinko_collector/README.md`
- Modify if required by verified live markup: parser fixture/tests and the smallest corresponding parser code.

**Interfaces:**
- Consumes: completed `cnlinko-collect` command.
- Produces: verified local catalog under `data/cnlinko_catalog/`.

- [ ] **Step 1: Add an opt-in live smoke test**

The test must fetch one list page, one product detail, and one download record; assert at least one model, parameter, image, and public document URL; and remain excluded from default offline tests by its `smoke_*_live.py` name.

- [ ] **Step 2: Run all offline tests**

Run: `python -m uv run pytest apps/cnlinko_collector/tests -q --ignore=apps/cnlinko_collector/tests/smoke_cnlinko_live.py`

Expected: all tests PASS.

- [ ] **Step 3: Run the bounded live probe**

Run: `python -m uv run pytest apps/cnlinko_collector/tests/smoke_cnlinko_live.py -q`

Expected: PASS without authentication or access-control bypass.

- [ ] **Step 4: Run metadata-only collection first**

Run: `python -m uv run --package cnlinko-collector cnlinko-collect --output data/cnlinko_catalog --metadata-only --min-interval 0.5`

Expected: nonzero product/model counts, populated per-model JSON, catalog indexes, and no unhandled exception.

- [ ] **Step 5: Audit metadata completeness before downloading files**

Compare reported site pagination totals with collected records; inspect at least one LP, YM, BD, DH, cable-assembly, cable, and accessory record; fix and retest any parser gap before proceeding.

- [ ] **Step 6: Download all assets with resume enabled**

Run: `python -m uv run --package cnlinko-collector cnlinko-collect --output data/cnlinko_catalog --assets-only --min-interval 0.5`

Expected: images/documents populate, `.part` count is zero after completion, and permanent failures appear in `reports/failures.csv`.

- [ ] **Step 7: Retry failures and verify idempotency**

Run: `python -m uv run --package cnlinko-collector cnlinko-collect --output data/cnlinko_catalog --retry-failures --min-interval 0.5`

Then rerun the same command and verify unchanged asset download counts remain zero.

- [ ] **Step 8: Inspect final outputs and document usage**

Verify XLSX opens, CSV row count equals model count, sampled image/PDF/DWG/STEP files are non-empty, hashes match the manifest, and README records run/resume/report commands plus known site-side omissions.

- [ ] **Step 9: Commit implementation documentation only**

```bash
git add apps/cnlinko_collector/README.md apps/cnlinko_collector/tests
git commit -m "test(collector): verify live cnlinko catalog collection"
```

Do not add `data/cnlinko_catalog/` to Git.
