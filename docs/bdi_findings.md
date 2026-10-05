# BDI hands-on findings

Dated measurements from building with the BDI API. Each one cost us a failed run or a dead end;
each failed run billed 0 credits unless noted.

## 2026-10-05: BigQuery target vs BigQuery source
- **Target** (`connection_type: gcloud`) works with BDI's managed service account and file zone.
  Grant that account BigQuery Admin on the project; no key, no bucket. Activation validated the
  connection and dataset.
- **Source** (`connection_type: bq_src`) is different, and the API creates it without complaint:
  1. With `custom_fz: false` the run fails: `[RVR-RDBMS-201] ... Unable to open keyfile: .../bq_src/<BDI account>@rivery-cloud-2017...json`.
     The managed key it looks for does not exist for the source connector.
  2. With our own key uploaded (`POST /connections/bq_src/files`) and `custom_fz: true`:
     `[RVR-BQ-RDBMS-001] BigQuery validation failed, missing field: default_bucket`.
  3. A bucket needs billing on the project (`403: The billing account for the owning project is disabled`).
  Net: BigQuery as a source needs a key file **and** a GCS staging bucket. The API tells you at run
  time, not at create time.

## 2026-10-05: Search Console via API (a legacy, UI-driven connector)
- Catalog flags it `is_new_interface: false`, `support_generic_ui: true`. Its report settings are
  in none of the 338 schemas in `https://api.rivery.io/openapi.json`; `source.additional_settings`
  is free-form and the create call accepts a body with no report at all.
- The connection itself is OAuth (browser consent), so it is created in the console. Everything
  after that was done by API, learning the grammar from the engine's own run errors:
  | Body | Run result |
  |---|---|
  | no report | `Missing Report! Please select one from the list.` |
  | `"report": "search_analytics"` | `Missing start date` |
  | + `start_date`, `end_date` | `'search_analytics'` (a lookup error: right key, wrong value) |
  | `"report": "analytics"` | succeeded, "No data retrieved" (date window was 70 seconds) |
- **The start date auto-advances.** After a run, `start_date` is overwritten with that run's end
  time (as Boomi's doc describes), so a probe run silently shrank the next window to seconds.
  `GET /rivers/{id}/runs/{run}/tasks` shows the dates actually sent (`input_parameters`). Run logs
  are "not available for google_search_console data source".
- The load leg then failed with `'NoneType' object is not iterable` until the target got an
  explicit column map (`target.single_table_settings.mapping`, entries `{"name","type"}`). An
  empty list did not help. With `ignore_unknown_values: true` on the target, mapping a subset of
  columns is enough.
- Working source settings: `{"report": "analytics", "start_date": "YYYY-MM-DD HH:MM:SS", "end_date": ...}`.
  Result: 24 rows, one per Search Console property, 0.5 credits per run (API source rate).
- `GET /rivers/{id}/runs` needs `start_time` and `end_time` query parameters.

## 2026-10-05: Integration -> BDI (Flow Service "kumoriBdiMonitor", built with Boomi Companion bc-integration 1.0.76)
- No native connector: aug9's Integration catalog has 292 connector types and none for BDI/Rivery.
  The bridge is the REST Client connector calling BDI's Rivers API.
- Companion steers REST Client over HTTP Client for new work ("Do not author a new HTTP Client
  component on agent judgment alone"); we followed it.
- Secret handling: REST connection auth NONE, the operation's `Authorization` header left blank, and
  the REST step fills it from DPP `DPP_BDI_AUTH` (`valueType="process"`), declared as an
  Environment Extension (`<PropertyOverride name="DPP_BDI_AUTH"/>`) on both processes. Companion
  documents this pattern; it does not document the XML for overriding a password-type Process
  Property component, so the DPP route was used. Tradeoff: a DPP extension value is readable by
  account admins through the Extensions API.
- Built through the API, pushed without errors: profile, REST connection, REST GET operation, FSS
  operation, `[SUB] BDI List Flows` (passthrough start, clear, GET, Notify, Return), wrapper
  `Flow ListFlows (FSS)` (FSS start, Process Call, Return), Flow Service `kumoriBdiMonitor`
  (basePath `kumoriBdiMonitor`, action `ListFlows`).
- **Deploy blocked by licensing on the trial account aug9-M3RGTZ.** Both processes:
  `HTTP 500 "This process cannot be deployed because it exceeds your available licenses for the
  Standard connector class by 1."` The REST Client counts as a Standard connector, and the
  Account API reports no licensing at all for this trial (status `trial`), so the trial grants 0.
  The Flow Service itself deployed (it holds no connector). As of 2026-10-05: the account with
  Boomi cloud access (aug9) has no connector licenses, and the accounts with licenses
  (1979: 50, boomimoneyball: 5 per class) return `400 "does not have access to cloud"` when a
  cloud atom is created.

## 2026-10-05: Flow API (Kumori BDI Monitor app, built entirely by API)
- The Flow API reference (manywho.github.io/docs-api) has no downloadable spec link; the full OpenAPI
  (357 schemas, 237 paths) is embedded in the page as Redoc state and parses with `raw_decode`.
- **Themes are API-creatable**: `POST /api/draw/1/element/theme` with `developerName`, `title`,
  `documentTitle`, `logoURL`, `cssContent` (and `properties` for design tokens, keys undocumented, so
  we styled with CSS only). The tenant had zero themes. Theme "kumori" applies at
  `/{tenant}/play/theme/kumori?flow-id=...` (page title becomes "Kumori").
- **Page elements need explicit container ids.** Leaving `pageContainers[].id` null fails:
  `400 "...has a page container ID of 00000000-... but a page container with that ID doesn't exist"`.
  Generate a GUID per container and set it on each component's `pageContainerId`.
- Flow create (`POST /api/draw/1/flow`) returns an `editingToken` and auto-creates a START map element.
  Map elements are created under `/api/draw/1/flow/{flow}/{editingToken}/element/map`; a page step is
  `elementType: "input"` with `pageElementId`. START is wired by POSTing it back with an `outcomes` entry.
- A transient `502 Bad Gateway` on map-element create: the element was NOT created (listed first, then
  retried once, 200). List before retrying to avoid duplicates.
- Publish = `POST /api/draw/1/flow/snap/{flow}` (new versionId, inactive), then
  `POST /api/draw/1/flow/activation/{flow}/{version}/true/true`.
- Run URLs answer identically on `flow.boomi.com` and `us.flow-prod.boomi.com` (player shell, 200).
- **Headless verification**: `POST /api/run/1` (flowId + versionId) then
  `POST /api/run/1/state/{stateId}` with `invokeType: FORWARD` and `selectedOutcomeId: null` auto-follows
  START to the page. Presentation HTML comes back in `pageResponse.pageComponentDataResponses[].content`,
  not in `pageComponentResponses`.

### 2026-10-05 (later): rebuilt on account 1979-44C86S, self-hosted runtime on GCP
- Runtime `boomi-runtime-1` (81ef8aa4-0585-49ca-819c-a96148aca5c1), Boomi `boomi/atom:release` v26.09.3 on a
  Container-Optimized OS VM in GCP project kumori-boomi-runtime, environment "Kumori GCP" (TEST).
- **COS gotcha:** a bind mount under `/mnt/stateful_partition` crash-loops the runtime with
  `./run: exec: line 3: atom: Permission denied`, because COS mounts that path `noexec`. Fix: a Docker named
  volume (lives under `/var/lib/docker`, exec allowed), copying the existing install so the runtime id is kept.
- **Licensing is fine on 1979:** `[SUB] BDI List Flows` (REST Client, Standard connector) packaged and deployed
  to the self-hosted runtime with no license error (the same process was refused on trial aug9).
- `DPP_BDI_AUTH` set through Environment Extensions (`boomi-extensions.sh set -`, value piped from .env, never
  written to a file); read back masked: set, starts with `Bearer `.
- **Test execution on the GCP runtime: COMPLETE.** The process log shows the BDI Rivers API response,
  `total_items: 3` (01, 02 and 03 "Kumori lane status (AI agent blueprint)"). Integration -> BDI works.
- **Flow Services Server is not available on 1979.** Its connector catalog has 291 types and no `fss` (aug9's
  292 includes "Boomi Flow Services Server"). Creating the FSS operation fails:
  `HTTP 400 subType fss is invalid`. So the FSS wrapper and the `kumoriBdiMonitor` Flow Service could not be
  created on 1979. "Web Services Server" (`wss`) is in 1979's catalog, so a WSS listener + Flow's OpenAPI
  connector is a possible alternative bridge to Flow (not built).

## 2026-10-05: self-hosted runtime on GCP (Container-Optimized OS) behind Cloudflare
- COS mounts /mnt/stateful_partition `noexec`; a Boomi bind mount there crash-loops with
  `./run: exec: line 3: atom: Permission denied`. A Docker named volume (under /var/lib/docker) works.
  The runtime still registered with the platform while crash-looping: "registered" is not "running".
- COS's host firewall is `-P INPUT DROP` (SSH only) and is rebuilt on boot; opening 443 needs an iptables
  rule from a startup script, in addition to the VPC firewall (which we limit to Cloudflare's IPv4 ranges).
- A local runtime's shared web server defaults to listener authType NONE. Set BASIC (plus external port 443,
  external SSL, override base URL) before deploying any listener.
- With no listener deployed, the runtime answers 404 on /ws/ and /fs/ paths before checking auth, so a
  404 there is not evidence that auth is off. Test auth against a deployed listener (expect 401 without creds).
- 1979's connector catalog has no Flow Services Server (fss) connector (291 types; aug9 has it). The bridge
  for Flow is a Web Services Server listener plus Flow's OpenAPI connector.

## 2026-10-05 (evening): the Flow -> Integration -> BDI bridge runs end to end
- Bridge: a Web Services Server listener (`GET /ws/simple/getListFlows`, process "WSS ListFlows Listener") wraps
  `[SUB] BDI List Flows` on runtime boomi-runtime-1, behind Basic auth, Caddy and Cloudflare at boomi.kumori.ai.
  Flow reaches it through its OpenAPI connector ("Kumori BDI Listener") and shows the rivers in a table on the
  Kumori BDI Monitor page. kumori.ai's "Run it live" button reads the same listener server-side.
- `checks/check_bdi_bridge.py`, as of 2026-10-05: PASS. Listener refuses anonymous (401); Integration -> BDI 3 rivers
  in 872 ms; kumori.ai live, 868 ms upstream; Flow table loaded 3 rivers, run 1,882 ms. The check was made to fail
  first (wrong listener path -> FAIL 404; wrong table name -> FAIL).
- Field notes:
  - Listener auth is checked only once a listener is deployed: before that the runtime answers 404 on every /ws/ path.
  - The listener token was set by API after the console route stalled twice on the clipboard (see platform_api_access.md).
  - kumori.ai first read the listener login from a secret it had no IAM grant on (403, surfaced as "not live yet").
    The login now lives in its own secret with a single per-secret grant, apart from the Platform API admin tokens.
  - kumori.ai first read BDI's field names wrong (`type`/`status` vs `river_type`/`river_status`); the test fixture
    had the same wrong shape, so it passed. It now uses the real response.
  - Flow's OpenAPI connector: four separate surprises, all in platform_api_access.md.
- The FSS build (aug9) needs a Flow Services Server connector (not in 1979's catalog) and Standard licenses (none on the trial), so it moved to
  `_antiquated/`. The WSS + OpenAPI route replaced it.
