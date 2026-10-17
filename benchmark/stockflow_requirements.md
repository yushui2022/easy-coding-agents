# StockFlow delivery contract

Build a maintainable inventory/order REST service in this repository, not a mock.
Python 3.11, FastAPI, Pydantic v2, SQLite (stdlib sqlite3), pytest, httpx, uvicorn.
All dependencies already installed. No installs or network access needed. Do not
read credentials, change AGENTS.md, commit or publish. Use real on-disk SQLite.

## Architecture and execution

Expose `stockflow.main.create_app(database_path: str, api_keys: dict[str, str])`.
The map is API token -> role ('admin' or 'viewer'). Independent app instances with
the same DB path share persisted state. Different paths must remain isolated.
Create/migrate schema idempotently in the factory, before the first request.
No DB connection global shared across requests. Foreign keys enabled, WAL and
bounded busy timeout; transactions serialize stock/idempotency changes. Close
connections reliably. Never use floats for money.

At least 8 meaningful production Python modules separating routes, schemas,
services, persistence and authentication. No fake filler modules. Implement error
mapping with stable HTTP codes, parameterized SQL, strict integer validation
(booleans/fractions are not quantities or prices), response models, pagination.
Add at least 20 meaningful local pytest tests, README, requirements.txt,
pyproject.toml and .gitignore. Document bootstrap, migrations, concurrency,
error responses, authentication, curl examples and remaining deployment limits.
Provide a uvicorn factory `create_default_app()` reading STOCKFLOW_DB and
STOCKFLOW_ADMIN_KEY; missing key must fail clearly, no hardcoded production key.

Only approved shell command: `python -B -m pytest -q -p no:cacheprovider`.
Write and run your tests. Existing project rules have already been provided;
avoid excessive discovery in this new repository. Implement complete files in
batches. Parallel delegation is optional; shared interface consistency matters
more than using subagents. Work until the system is implemented and verified.

## Public endpoints

All endpoints except GET /health and OpenAPI/docs require header X-API-Key.
Missing/invalid key => 401; viewer reads permitted, all writes => 403.
GET /health => 200 and {"status":"ok"}. API errors never expose SQL or secrets.

### Products
POST /products (admin) accepts {sku, name, price_cents, stock}, returns 201 object
with integer id, sku, name, price_cents, stock, version (initially 1).
sku/name must be trimmed nonempty strings; sku unique (409 duplicate).
price_cents and stock strict nonnegative integers. Unknown fields => 422.
GET /products/{id} => product or 404.
GET /products?limit=20&offset=0&q= => {items:[products],total:int}; ascending id,
limit 1..100, offset>=0; q case-insensitive substring of name or sku, parameterized
SQL and literal matching (SQL quotes must not inject).
PATCH /products/{id} accepts {expected_version, name?, price_cents?}; admin,
optimistic concurrency: version mismatch 409, update increments version exactly
once. No stock changes through PATCH. Other invalid fields => 422.

### Inventory
POST /inventory/adjustments (admin) accepts {product_id, delta, reason}, delta
strict nonzero integer, reason trimmed nonempty. Returns 201 with product_id,
delta, stock (resulting stock). Missing product 404, insufficient stock 409.
Adjustment updates product version and writes audit in the SAME transaction.

### Orders
POST /orders (admin), REQUIRED nonblank Idempotency-Key header (missing => 400).
JSON {customer: nonempty string, items:[{product_id, quantity:positive strict int}]}.
At least one line; duplicate product lines => 422; no unknown fields.
Atomically check and decrement all stocks, create order and price snapshots,
record audit and idempotency. Missing product =>404, shortage=>409; rollback all
effects on failure. Failed attempts must not consume the idempotency key.
Return 201 for first create, 200 for identical replay, 409 for same key with a
different body. Replay survives app recreation, ignores JSON object key order
but line array order may be significant. Concurrent identical keys return one
order and decrement stock once. Orders have integer id, customer, status
'confirmed', total_cents, items with product_id, quantity, unit_price_cents.
Stock updates increment product version. Snapshot prices do not change when
the catalog changes. GET /orders/{id} => object or404. GET /orders?limit=20&offset=0
=> {items,total}, ascending id, same pagination validation.
POST /orders/{id}/cancel =>200 order status 'cancelled'; return inventory exactly
once even with repeated/concurrent cancellation; write one cancellation audit.
Unknown order=>404. Cancellation must be durable across app recreation.

### Reports and audit
GET /reports/summary => {products,stock_units,confirmed_orders,revenue_cents}.
Count current products and stock; revenue only confirmed orders, from snapshots.
GET /audit?limit=20&offset=0 => {items,total}; ascending id, each event has id,
action, entity_id, created_at. Required actions: product_created, product_updated,
stock_adjusted, order_created, order_cancelled. Failed transactions and replays
must not duplicate audit entries. Do not add audit writes for read requests.
GET /export/products.csv => text/csv with columns
id,sku,name,price_cents,stock,version. Correct CSV quoting. Prevent spreadsheet
formula injection: prefix apostrophe for sku/name starting =,+,-,@ after trimming.

## Acceptance emphasis

No overselling under concurrent orders from separate app instances. No double
restock. Multi-line failure rolls back earlier lines. Idempotency conflict is
separate from stock failure. Permission checks cover every route. Use structured
HTTP responses, not tracebacks. Local tests must exercise those business cases.
