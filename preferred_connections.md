# Preferred BDI connections

Read by Boomi Companion's bc-bdi skill before it proposes a connection.

| Name | Type | Use |
|---|---|---|
| kumori-bdi-sandbox | Google BigQuery (Target), `gcloud` | Default target for every pattern. GCP project `kumori-bdi-sandbox` (BigQuery sandbox, no billing, tables expire after 60 days), dataset `bdi_patterns`, region US, BDI-managed file zone. Created via API 2026-10-05. |
