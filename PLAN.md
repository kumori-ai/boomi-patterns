# 14-day BDI sprint

Trial: 2026-10-05 to 2026-10-19, 1,000 credits, whichever runs out first. Goal: hands-on with
every major BDI feature, each one ending as a checked pattern or a dated finding, plus the
how-tos that teach it.

Feature map source: research digest of 2026-10-05 (help.boomi.com Data Integration docs,
pricing FAQ, Rivers API). Items marked (unverified) get confirmed hands-on before any write-up
states them.

## Credit budget (BDU, pricing FAQ as of 2026-10-05)
| Activity | Cost |
|---|---|
| API source | 0.5 per output table per run, +0.5 per extra 50MB |
| Database / file source | 1 per 100MB |
| Log-based CDC | 2 per 100MB |
| Logic river run | 0.5 per run |
| Python step | 0.021 (XS) to 0.492 (XXXL) per minute, +0.4 per 100MB network |

Rules: manual runs only, no schedules until day 9, small datasets (under 50MB), log every run's
credits in `notes/credits.md`. A single hourly schedule on a 4-table API river is
4 x 0.5 x 24 = 48 credits a day, so schedules get turned off the same day they are tested.

## Days
| Day | Focus | Pattern / output |
|---|---|---|
| 1 | Destination (BigQuery sandbox), first Source to Target river from a public REST API | `patterns/01_rest_to_warehouse` + getting-started how-to |
| 2 | Loading modes: overwrite, append, upsert-merge (merge may fail in sandbox, unverified) | `02_loading_modes` |
| 3 | Incremental extraction, column mapping, expressions, schema drift | `03_incremental` |
| 4 | Custom REST connector: Blueprint and the Data Connector Agent (AI, 2026) | `04_custom_connector` |
| 5 | Logic rivers: SQL steps, branching, sub-flows | `05_logic_orchestration` |
| 6 | Python steps (smallest server size) | `06_python_transform` |
| 7 | Variables and environments (trial has 2) | `07_environments` |
| 8 | Action rivers and reverse ETL | `08_reverse_etl` |
| 9 | Scheduling, dependencies, alerts, monitoring, BDU dashboard | `09_operations` |
| 10 | Rivers API + CLI (YAML): rivers as code in git | `10_rivers_as_code` |
| 11 | CDC / database replication, if a free source exists (unverified) | `11_cdc` |
| 12 | Kits / templates, data quality tests | `12_quality` |
| 13 | End-to-end: one of Rivery's six use cases built start to finish | showcase pattern |
| 14 | Write-ups: README index, how_we_made_this.md, gaps found in bc-bdi | ready to share |

Every day: build with bc-bdi, write a check, record what broke, record credits spent.

## Kumori track (drink our own champagne)
BDI never connects to the shared Cloud SQL. Data leaves kumori-404602 only as GCS exports or
BigQuery federated reads, each disclosed before it is set up, operational tables only (no chat
logs, no visitor IPs, no user content). Lands in `kumori-bdi-sandbox`.

Mapped to the problem patterns in Rivery's own case studies (17 read 2026-10-05, rivery.io/stories):
| Customer pattern | Kumori chapter |
|---|---|
| Operational DB to cloud warehouse (most common) | Replicate kumori's operational tables (5.4 GB, 14 schemas as of 2026-10-05) |
| Replace hand-written scripts | Rebuild the daily cost snapshot and reconciliation jobs as rivers (verify they are hand-built ETL first) |
| Consolidate SaaS and marketing data | Search Console + GitHub (GA4 already exports to BigQuery natively) |
| Unify scattered telemetry | 6 LLM cost/usage tables and 2 visitor logs into one model |
| CDC for freshness | Not on kumori (needs a direct DB connection). Demo on a free sample DB instead |
| Reverse ETL | "Send By Email" target as a fleet digest, within the shared-sender rules |

Stretch: dos_bros `rig_results.sqlite` on the ROG (2,751 renders, 24,362 metric rows as of 2026-10-05).

## Known gotchas to hit on purpose (practitioner reviews, 2026-10-05, mostly vendor-adjacent sources)
- Credits have no ceiling; CDC bills 2x; Python bills separately by runtime and server size.
- No built-in lineage or impact analysis; logging and data visibility called weak. Build our own.
- Incremental merge logic misbehaved for at least one reviewer; CDC and Python needed support help.
- Drag-and-drop gets painful in complex rivers: argues for rivers-as-code via API from day 1.
- API and CLI are Professional-plan features; Base (the only self-serve paid plan) has neither.
