# Ozon API client

Thin Python wrapper for the official Ozon Seller API.

This tool is intentionally small: it centralizes authentication, JSON POST
requests, error handling, and first-phase Seller API endpoints for Ozon FBS
dropshipping operations.

## Current scope

Wrapped endpoints:

| Method | Endpoint | Use |
|---|---|---|
| `list_warehouses()` | `POST /v1/warehouse/list` | Get seller warehouses |
| `import_products(items)` | `POST /v3/product/import` | Create/update product cards |
| `import_prices(prices)` | `POST /v1/product/import/prices` | Batch update prices |
| `update_stocks(stocks)` | `POST /v2/products/stocks` | Batch update stock |
| `list_unfulfilled_fbs(...)` | `POST /v3/posting/fbs/unfulfilled/list` | Pull FBS orders waiting for action |
| `get_fbs_posting(posting_number)` | `POST /v3/posting/fbs/get` | Get FBS order detail |
| `ship_fbs(payload)` | `POST /v2/posting/fbs/ship` | Ship/package FBS posting |
| `get_fbs_package_label(posting_numbers)` | `POST /v2/posting/fbs/package-label` | Get package labels |
| `cancel_fbs_posting(...)` | `POST /v2/posting/fbs/cancel` | Cancel FBS posting |

Any missing Seller API endpoint can be called with:

```python
client.request("/some/ozon/path", {"payload": "value"})
```

## Usage

```python
from ozon_api import OzonSellerClient

client = OzonSellerClient(
    client_id="YOUR_CLIENT_ID",
    api_key="YOUR_API_KEY",
)

warehouses = client.list_warehouses()
orders = client.list_unfulfilled_fbs(limit=50)
```

Use `PYTHONPATH=tools` when running from the repository root:

```powershell
$env:PYTHONPATH = "tools"
python -c "from ozon_api import OzonSellerClient; print(OzonSellerClient)"
```

## Tests

No third-party test dependency is required.

```powershell
$env:PYTHONPATH = "tools"
python -m unittest tools.ozon_api.tests.test_seller_client
```

