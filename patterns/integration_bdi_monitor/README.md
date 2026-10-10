# Integration -> BDI monitor (Boomi Integration calling the BDI Rivers API, served as a listener)

A Boomi Integration process reads Boomi Data Integration's pipelines (BDI calls them data flows; its API says rivers) through the BDI Rivers API and serves them
as an authenticated Web Services Server listener, `GET /ws/simple/getListFlows`. Two clients use it: Boomi Flow,
through its OpenAPI connector (`../flow_bdi_monitor`), and kumori.ai's "Run it live" button.

Built with Boomi Companion bc-integration 1.0.76. No credential is in any component: the REST step fills
`Authorization` from `DPP_BDI_AUTH`, set only through Environment Extensions, and the listener's Basic auth is the
runtime's shared web server user, whose token is set by `tools/store_sws_token.sh`.

**These XMLs are Kumori's own live components as they ran**, with the account's ids replaced by named placeholders
(`{{FOLDER_ID}}`, `{{PROFILE_ID}}`, `{{BDI_ACCOUNT_ID}}` and so on). Every token and password lives in Secret Manager.
To reuse: create the components in order (profile, connection, operation, subprocess, WSS operation, wrapper) and
fill each placeholder with the id your account returns, as `active-development/.../create_all.sh` did.

| File | What it is |
|---|---|
| `j.BDI.ListRivers.RESP.xml` | JSON profile of the Rivers API list response |
| `BDI_API_Connection.xml` | REST connection to api.rivery.io |
| `BDI_GET_Rivers_List.xml` | REST GET operation for the rivers list |
| `SUB_BDI_List_Flows.xml` | "[SUB] BDI List Pipelines": GET the pipelines, return the documents (testable on its own) |
| `WSS_ListFlows.xml` | "[WSS] BDI List Pipelines": GET, objectName `ListFlows` (kept: it is the URL path callers use), JSON out |
| `WSS_ListFlows_Wrapper.xml` | "[LISTENER] BDI List Pipelines": WSS start -> call the subprocess -> return documents |
| `wss_list_flows.openapi.yaml` | OpenAPI 3.0 description of the listener, for Flow's OpenAPI connector |

## Live instance (as of 2026-10-05)
Environment "Kumori GCP", runtime boomi-runtime-1 (self-hosted, Container-Optimized OS on GCP, behind Caddy and
Cloudflare at https://boomi.kumori.ai).

| Component | Placeholder in the XMLs | State |
|---|---|---|
| Folder "Kumori BDI Monitor" | `{{FOLDER_ID}}` | |
| Profile j.BDI.ListRivers.RESP | `{{PROFILE_ID}}` | |
| REST connection "BDI API (api.rivery.io)" | `{{CONNECTION_ID}}` | |
| REST op "BDI Rivers API: List Pipelines" | `{{REST_OPERATION_ID}}` | |
| Process "[SUB] BDI List Pipelines" | `{{SUB_PROCESS_ID}}` | deployed |
| WSS op "[WSS] BDI List Pipelines" | `{{WSS_OPERATION_ID}}` | |
| Process "[LISTENER] BDI List Pipelines" | `{{LISTENER_PROCESS_ID}}` | deployed |

Check: `python3 checks/check_bdi_bridge.py` (as of 2026-10-05: PASS, 3 rivers, 872 ms through the listener).

## Field notes
- The runtime's shared web server defaults to listener auth NONE. Set BASIC before deploying any listener.
- With no listener deployed the runtime answers 404 on every /ws/ path before checking auth, so a 404 says nothing
  about auth. Test against a deployed listener: 401 without credentials, 200 with them.
- Flow Services Server (FSS) is the classic Flow-to-Integration bridge, but it is not in every account's connector
  catalog (ours has none: `subType fss is invalid`), and a trial account has no Standard connector licenses
  to deploy it. A Web Services Server listener plus Flow's OpenAPI connector works on any account, and is the route
  this pattern uses.
