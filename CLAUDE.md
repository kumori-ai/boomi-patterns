# boomi-patterns -- project rules

Public repo (planned: `kumori-ai/boomi-patterns`, not pushed yet). Working, checked patterns for
Boomi Data Integration (BDI, formerly Rivery), later Flow and MFT, plus the how-tos and write-ups
that teach them. Audience: Boomi PSO and partner leads first, then customers who find it on
their own. Unofficial: never imply Boomi endorses it, never name a fork or tool "Boomi".

## Rules specific to this project
- **API first, never hand Andy a manual step the API can do** (Andy, 2026-10-05: "NEVER ask me
  to do something manually that you can do via API, that's exactly what we're doing here").
  The repo's whole claim is that BDI can be driven end to end by automation. Before asking for a
  console click, check the Rivers API and the bc-bdi scripts. A step is console-only only after
  that check, and the write-up records it as a platform gap (e.g. token generation, Blueprint
  recipes, browser-consent OAuth, kits).
- **A pattern exists only if it ran.** Every pattern in `patterns/` has a check in `checks/`
  and a dated result ("as of 2026-10-07, ran in 41s, 12,400 rows"). No pattern documented
  from the docs alone.
- **Field notes, framed as expertise.** Each pattern's write-up ends with field notes: what a team should know before
  building the same thing. Same facts, stated as know-how, never as a list of what broke (Andy, 2026-10-05: "the point
  is that we are good at BDI and have a clean way to do it"). Public copy (repo, kumori.ai, the Flow app) is confident.
- **Boomi Companion stays upstream.** `bc-bdi` is enabled in `.claude/settings.json` and is
  used for every build step. Never vendor or edit it; our layer sits beside it. Feedback on it
  goes to developer-offerings@boomi.com, not a fork.
- **Public vs private.** Anything from Boomi staff conversations (people, staffing, procurement,
  customers) and anything about the trial account lives in `notes/` (gitignored). Exported river
  JSON is scrubbed of account ids, environment ids, connection ids and hostnames before commit.
- **Credentials.** The BDI API token is `KUMORI_BOOMI_BDI_API_TOKEN` in kumori-404602 Secret Manager; Boomi Platform API tokens are `KUMORI_BOOMI_INTEGRATION_API_TOKEN`, runtime listener logins `KUMORI_BOOMI_INTEGRATION_LISTENER` (the only one kumori.ai can read), Flow keys `KUMORI_BOOMI_FLOW_API_KEY`.
  `tools/make_env.sh` writes the gitignored `.env` the skill expects. Never paste a token into
  a file by hand.
- **Isolated data only.** Sources are public APIs, sample data or synthetic data. Never the
  kumori Cloud SQL (BDI is SaaS and would need its IPs allowlisted), never ServiceNow data or
  systems, never Andy's personal data. The destination is one isolated free-tier target with
  its own scoped credential, disclosed before it is created.
- **Free only.** The BDI trial is 14 days and 1,000 credits, no card. Track credit burn in
  `notes/`; nothing converts to paid without Andy's explicit yes.
- Scratch goes in `_oneoff/`. Nothing is pushed to GitHub until Andy says so.
