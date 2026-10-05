# boomi-patterns

Working, checked patterns for Boomi Data Integration (BDI, formerly Rivery), Boomi Integration and Boomi Flow,
built and driven entirely by API, with the field notes that make the next build fast. By Kumori (https://kumori.ai),
who design and build integrations on the Boomi platform.

**Unofficial.** Not made, reviewed or endorsed by Boomi. Built on Boomi Companion
(github.com/OfficialBoomi/boomi-companion), used as published.

## The rule here
A pattern exists only if it ran. Each one has a check in `checks/` and a dated result. Nothing is documented from
the docs alone, and every write-up ends with field notes: what a team should know before building the same thing.

## Patterns
| Pattern | What it proves | Check, as of 2026-10-05 |
|---|---|---|
| `patterns/integration_bdi_monitor` | Boomi Integration reads BDI's flows through the Rivers API and serves them as an authenticated listener | `checks/check_bdi_bridge.py`: PASS, 3 rivers, 872 ms |
| `patterns/flow_bdi_monitor` | A Boomi Flow app explains the chain, asks BDI for its pipelines at the press of a button, and opens any one for detail, through Flow's OpenAPI connector and the Integration listener | same check: PASS, button pressed, 3 rivers |

Together they make one chain, and kumori.ai's "Run it live" button uses the same listener:
`Flow page -> OpenAPI connector -> Cloudflare -> Integration runtime (GCP) -> process -> BDI Rivers API`.

Try it: [the live Flow app](https://us.flow-prod.boomi.com/c0bdf205-0a20-4865-8a4e-5bb408d5ba0b/play/theme/kumori?flow-id=0438716c-4fa5-447c-9779-4a93924aa80b).

## The runtime, built the way we build for clients
Boomi's official runtime container on Google's Container-Optimized OS (Shielded VM, no service account), in a project
of its own. The firewall admits only Cloudflare's ranges on HTTPS and Google's Identity-Aware Proxy for admin access
(no open SSH port). TLS runs end to end with a Cloudflare origin certificate, the reverse proxy answers only Boomi's
listener paths, every listener call signs in, and every secret lives in Google Secret Manager, readable only by the
service that uses it and rotated by `tools/store_sws_token.sh`.

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
