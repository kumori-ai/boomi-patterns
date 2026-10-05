# Flow -> Integration -> BDI monitor (Boomi Flow showing BDI's flows, read through Boomi Integration)

A Boomi Flow app, "Kumori BDI Monitor", with one page whose table lists Boomi Data Integration's flows live. The
table loads through Flow's OpenAPI connector, which calls the Integration listener in `../integration_bdi_monitor`.
Everything here was created through the Flow API; no step needed the Flow console.

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
4. Page: a `table` component bound to type `BDI Flow List:items` and its `/ws/simple/getListFlows` binding.
5. Snapshot, activate, run headlessly (`checks/check_bdi_bridge.py`): the table loads 3 rivers.

Full detail and every error met on the way: `docs/platform_api_access.md`.

## What tripped us up
- The connector has no outbound Basic auth field. Declare an `apiKey` scheme on the `Authorization` header on the
  operation itself (root-level `security:` alone was ignored) and put the whole `Basic ...` value in API Key.
- Config fields given as plain strings fail with a misleading "Schema URL or Schema Value hasn't been correctly
  configured", even for a public spec URL.
- Installing the connector generates no types by itself; the type table is a separate, undocumented step.
