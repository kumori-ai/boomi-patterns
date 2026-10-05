# Flow -> Integration -> BDI monitor (Boomi Flow showing BDI's flows, read through Boomi Integration)

A Boomi Flow app, "Kumori BDI Monitor", that tells its own story in three screens:
1. **What you're looking at**: who Kumori is, the four hops a click travels (Flow, Cloudflare, Boomi Integration on
   our GCP runtime, Boomi Data Integration), how the runtime is hardened, and one button: *Ask BDI for its pipelines*.
2. **Pipelines**: the live answer, stamped with the time it was fetched, in a striped table with *Open*, *Ask again*
   and *Start over*.
3. **One pipeline**: type, status, last update and id, with *Back* and *Check again*.

Data loads through Flow's OpenAPI connector, which calls the Integration listener in `../integration_bdi_monitor`.
Everything here was created through the Flow API; no step needed the Flow console.
The full story behind it: [kumori.ai/whats-new/boomi-data-integration](https://kumori.ai/whats-new/boomi-data-integration).
[Open the live app](https://us.flow-prod.boomi.com/c0bdf205-0a20-4865-8a4e-5bb408d5ba0b/play/theme/kumori?flow-id=0438716c-4fa5-447c-9779-4a93924aa80b).

**This is Kumori's own live tenant (niftyg, c0bdf205-0a20-4865-8a4e-5bb408d5ba0b), ids included.** The export was
scrubbed: Flow exports a Password value's default in plain text, and our listener credential was in it.

| File | What it is |
|---|---|
| `kumori_bdi_monitor.flow-package.json` | Flow package (flow, page, connector, types, values, OpenAPI config), credential redacted |
| `kumori.theme.json` | The Kumori theme |
| `../integration_bdi_monitor/wss_list_flows.openapi.yaml` | The OpenAPI 3.0 spec the connector reads |

## How it was built, by API (as of 2026-10-05)
1. Two Value elements: the spec as `ContentCode`, and `Basic <base64 user:token>` as `ContentPassword`.
2. Connector: `POST /api/draw/1/element/service` with uri `flow://openapi`, `elementType: SERVICE`, and config
   fields **referencing** those Values (Schema Value, API Key).
3. Type table: `GET /api/draw/1/openapi/info/<schemaValueId>?serviceId=<id>`, mark the endpoint
   `shouldGenerateType`, name the response type, set `listFilterMapping.listProp = "items"`, save with
   `POST /api/draw/1/element/openapi`, then `POST /element/service/install` with the `openApiId` and save the
   service with the returned types. Undocumented; found in the Flow composer's JavaScript.
4. Story: three Values (`BDI pipelines` list, `Selected pipeline`, `Fetched at`), three pages, and map elements
   Start -> intro -> `database_load` (Load into `BDI pipelines` through the connector binding) -> `operator` (stamp
   `Fetched at` from `$State` Date Modified) -> pipelines page (table bound to the list, row outcome *Open* saves the
   selection) -> detail page. Element type names are snake_case (`database_load`), as the composer sends them.
5. Theme `kumori`: CSS for cards and striped tables, plus a small DOM helper in the theme's JavaScript that turns ISO
   times into "2 hours ago" (full time on hover), snake_case into words, and status into a glyph-and-text badge.
6. Snapshot, activate, and run headlessly (`checks/check_bdi_bridge.py` presses the button and reads the rows).

Full API detail: `docs/platform_api_access.md`.

## Field notes
- The connector has no outbound Basic auth field. Declare an `apiKey` scheme on the `Authorization` header on the
  operation itself (root-level `security:` alone was ignored) and put the whole `Basic ...` value in API Key.
- Config fields given as plain strings fail with a misleading "Schema URL or Schema Value hasn't been correctly
  configured", even for a public spec URL.
- Installing the connector generates no types by itself; the type table is a separate, undocumented step.
- Pressing an outcome through the run API needs a page request object, even an empty one; with none, Flow stays put.
- Save Values and Pages by looking them up by name first: `updateByName` does not stop duplicates on create.
