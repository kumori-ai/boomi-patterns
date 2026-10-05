# Boomi Platform API access (Integration, Flow, MFT side)

How the Boomi Enterprise Platform is driven by API, separate from BDI (which has its own console,
API and tokens). Verified against Boomi's docs on 2026-10-05.

## Tokens
- Created only in the UI: **Settings > My User Settings > Platform API Tokens > Add New Token**,
  name it, **Generate Token**, copy it. The full value is never shown again. (Platform gap: no API
  creates a token.)
- Prerequisites: the user has the **API Access** privilege and the **API Token** feature is enabled.
- Up to five tokens per user. A token belongs to the user who made it and cannot be updated, only
  renamed, disabled, enabled or revoked. Account admins can manage every user's tokens under
  **Settings > Boomi Platform API > Token Management**.
- Source: help.boomi.com, "Platform API Tokens overview" (updated 30 July 2026).

## Calling the API
- Basic auth, user field `BOOMI_TOKEN.<username>`, password field the token:
  `curl --user "BOOMI_TOKEN.<username>:<token>" https://api.boomi.com/api/rest/v1/<accountId>/<Object>/...`
- `api.boomi.com` is the North American platform; Europe is `api.platform.gb.boomi.com`.
- `<accountId>` is the authenticating account, e.g. `name-XXXXXX` from Settings > Account Information.
- Boomi Companion's scripts use the same scheme (`boomi-common.sh`: `BOOMI_TOKEN.${BOOMI_USERNAME}:${BOOMI_API_TOKEN}`
  against `${BOOMI_API_URL}/api/rest/v1`).

## Doc drift found
Companion's onboarding guide (bc-integration, as of 2026-10-05) says "Settings > Account Information
and Setup > AtomSphere API Tokens". The live UI and help docs say **Settings > My User Settings >
Platform API Tokens**.

## Measured 2026-10-05
- **A Platform API token works only on the account it was created in.** A token made while signed in
  to one account returned 200 on `GET /Account/<that account>` and 403 `error.user.auth` on two other
  accounts the same user belongs to. One token per account.
- The username in `BOOMI_TOKEN.<username>` is the login email exactly as Boomi shows it (Flow's User
  Settings page displays it).
- Responses are XML unless the request sends `Accept: application/json`.
- `GET /Account/<id>` returns licensing (purchased/used per connector class), status, dateCreated,
  supportLevel. `POST /Role/query` with `{}` lists every role, including MDM, API Management and
  Event Streams roles.

# Boomi Flow API (separate host, separate key)
Verified against help.boomi.com "Using API keys" worked example (updated 23 July 2026).

- Keys are created only in the Flow UI: the user icon (top right) > **User Settings** >
  **Generate a new API key**: give it a Key Name, pick the Tenant, generate, then **Show** in the
  Key column and copy. (Platform gap: no API creates a Flow key.)
- A key is scoped to the tenant chosen when it was made.
- Every request carries two headers: `x-boomi-flow-api-key: <key>` and `manywhotenant: <tenant id>`.
- Example from the docs: `GET https://flow.boomi.com/api/draw/1/flow` lists every flow in the tenant.
- Measured 2026-10-05: a US key answers identically on `flow.boomi.com` and `us.flow-prod.boomi.com`.
- Measured 2026-10-05: **the key's own tenant wins over the `manywhotenant` header.** A key made for
  tenant A, sent with tenant B's id in `manywhotenant`, returned tenant A's flows and tenant record
  with HTTP 200, not an error. Check `GET /api/admin/1/tenant` to see which tenant a key really hits.
  One key per tenant.
- `GET /api/admin/1/tenant` returns the tenant record and its feature flags; `GET /api/draw/1/element/service`
  and `.../element/type` list connectors (services) and types.
- The tenant id is the GUID in the Flow URL: `https://us.flow-prod.boomi.com/<tenant id>/flows`.

## Revoking tokens (platform gap)
- Revoking or deleting a token is UI-only: the owner via the gear icon on **My User Settings >
  Platform API Tokens**, or any account administrator via **Settings > Boomi Platform API > Token
  Management** (search by user, name, or the first 6 characters). Boomi's "API Token Management"
  page (updated 23 June 2025) describes no Platform API object for it, and none was found.
- The Platform API Tokens page lists the **signed-in user's** tokens, not the account's. Measured
  2026-10-05: a token made while the wrong user was signed in authenticated as that user (HTTP 200),
  even though the right account was selected. Check the account switcher first: it lists only the
  accounts the signed-in user belongs to.
- Measured 2026-10-05: `GET /api/admin/1/users` lists the tenant's users with their role
  (`developerName: ADMINISTRATOR`), so Flow tenant user management is reachable by API, unlike
  Platform API tokens. `/api/admin/1/tenant/users` is 404.

## Runtime listener (shared web server) tokens: settable by API
Measured 2026-10-05 on a self-hosted runtime (account 1979-44C86S, runtime 81ef8aa4-0585-49ca-819c-a96148aca5c1):
- `GET /SharedWebServer/<runtimeId>` lists `userManagement.users[]` but never returns a token.
- `POST /SharedWebServer/<runtimeId>` with `users[].token` set **accepts a caller-chosen token** (HTTP 200), and a
  deployed WSS listener answered 200 with it on the first try (~10 s later). So the "Generate Token" button is not
  the only way: rotation is fully scriptable. `tools/store_sws_token.sh` does it (set, verify 200, store, destroy old).
- Earlier notes in this repo called this console-only. That was wrong, inferred from the UI, never tested.

# Boomi Flow OpenAPI connector, driven by API
Measured 2026-10-05 on tenant niftyg (c0bdf205-0a20-4865-8a4e-5bb408d5ba0b). The Draw API documents the install
calls; the type table the UI calls "Configure OpenAPI" is **not** in the public API spec (manywho.github.io/docs-api).
It was found in the composer's own JavaScript (`/assets/flow-admin.js`).
- Connector uri is `flow://openapi`. `POST /api/draw/1/element/service/configurationValues` with that uri lists its
  fields: Schema URL, Schema Value, OAuth2/OIDC Client Id and Secret, Authorization Groups and Users, API Key.
- **Config fields must reference Value elements**, not hold strings: `{"developerName": "Schema Value",
  "valueElementToReferenceId": {"id": <value id>}}`. Raw `contentValue` strings, even a public petstore URL, fail with
  `500 "Schema URL or Schema Value hasn't been correctly configured"`.
- `POST /api/draw/1/element/service` needs `elementType: "SERVICE"` (400 otherwise, not in the spec as required).
- Type table (undocumented): `GET /api/draw/1/openapi/info/<schemaValueId>?serviceId=<id>` returns one row per
  endpoint; set `shouldGenerateType: true`, `responseSchema.developerName`, and for a GET-into-table
  `responseSchema.listFilterMapping: {"listProp": "items"}`; save with `POST /api/draw/1/element/openapi`; then
  `POST /element/service/install` with `openApiId` returns the generated `typeElements`; save the service with them.
- **Basic auth to the API works through the API Key field.** The connector has no field for outbound Basic auth (its
  Basic option is for signing users in to Flow). Declaring an `apiKey` security scheme `in: header, name:
  Authorization` *on the operation* (a root-level `security:` alone was ignored: the endpoint showed no scheme) and
  putting `Basic <base64 user:token>` in the API Key value made Flow's table load 3 rows from a listener that answers
  401 without credentials.
- `POST /api/run/1/service/data` fails `400 "Value cannot be null (input)"` outside a run. Inside one, take the table's
  `objectDataRequest` from the page response, add the state token, and it loads.
- **A Flow package export (`GET /api/package/1/flow/<id>/<version>`) contains a Password-typed Value's default in
  plain text.** Our listener credential was in it. Scrub every export before committing; this repo's export was
  redacted and checked against the live secret values.

## Flow players by API (measured 2026-10-05)
- `GET /{tenant}/player` lists players (`["default"]` on a new tenant); `GET /{tenant}/play/{name}` returns a player's HTML.
- `POST /{tenant}/play/{name}` creates or updates one. Body: `application/x-www-form-urlencoded; charset=UTF8`, a literal `=` then the
  URL-encoded HTML (the spec's "=player content goes here"). Sent as a normal form field, it fails with "Form key length limit 2048".
- The default player is ~40 lines: a `<base href=".../runtime/nextgen/">`, `assets/flow.css`, `assets/flow.js` and `<div id="flow-app">`.
  Our `kumori` player wraps that with kumori.ai's header, Google Fonts, styles and footer; Boomi's docs say a player can be customized completely.
