# boomi-patterns

Working, checked patterns for Boomi Data Integration (BDI, formerly Rivery), Boomi Integration and Boomi Flow,
built and driven by API, with a record of what broke on the way. By Kumori (https://kumori.ai).

**Unofficial.** Not made, reviewed or endorsed by Boomi. Built on Boomi Companion
(github.com/OfficialBoomi/boomi-companion), used as published.

## The rule here
A pattern exists only if it ran. Each one has a check in `checks/` and a dated result. Nothing is documented from
the docs alone, and every write-up keeps its "what tripped us up" section.

## Patterns
| Pattern | What it proves | Check, as of 2026-10-05 |
|---|---|---|
| `patterns/integration_bdi_monitor` | Boomi Integration reads BDI's flows through the Rivers API and serves them as an authenticated listener | `checks/check_bdi_bridge.py`: PASS, 3 rivers, 872 ms |
| `patterns/flow_bdi_monitor` | A Boomi Flow page lists BDI's flows live, through Flow's OpenAPI connector and the Integration listener | same check: PASS, Flow table loaded 3 rivers |

Together they make one chain, and kumori.ai's "Run it live" button uses the same listener:
`Flow page -> OpenAPI connector -> Cloudflare -> Integration runtime (GCP) -> process -> BDI Rivers API`.

## Findings that go beyond the docs (2026-10-05)
- A runtime listener's token can be set by the Platform API (`SharedWebServer` UPDATE), not only by the console button.
- Flow's OpenAPI connector type table runs on undocumented `/api/draw/1/openapi/info` endpoints, and outbound Basic
  auth works through the API Key field on an `Authorization` header scheme.
- A Flow package export contains a Password value's default in plain text.
Details: `docs/platform_api_access.md`, `docs/bdi_findings.md`.

## Ids are real, secrets are not here
The XMLs, exports and docs show Kumori's own live account, runtime, tenant and component ids, so every claim can be
traced. No token, key or password is in this repo: they live in Google Secret Manager, `tools/make_env.sh` writes a
gitignored `.env` for Boomi Companion, and every export is scrubbed and checked against the live secret values before
it is committed.

## Layout
`patterns/` checked patterns · `checks/` the scripts that prove them · `docs/` findings · `tools/` setup and
credential rotation (Secret Manager, never files) · `preferred_connections.md` read by Companion's bc-bdi skill.
