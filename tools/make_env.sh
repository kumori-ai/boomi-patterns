#!/usr/bin/env bash
# Writes the .env that Boomi Companion's skills read (bc-bdi: BDI_*, bc-integration: BOOMI_*).
# Secrets live in kumori-404602 Secret Manager:
#   KUMORI_BOOMI_BDI_API_TOKEN         the BDI token
#   KUMORI_BOOMI_INTEGRATION_API_TOKEN JSON {"username", "api_url", "tokens": {accountId: token}}
# The BDI ids come from the BDI console URL:
#   https://console.rivery.io/dashboard/<account id>/<environment id>/dashboard
# Usage: tools/make_env.sh <bdi_account_id> <bdi_environment_id> <boomi_account_id> [extra BOOMI_ lines...]
#   extra lines, e.g. BOOMI_ENVIRONMENT_ID=... BOOMI_TEST_ATOM_ID=..., are appended verbatim
set -euo pipefail
cd "$(dirname "$0")/.."

bdi_account_id="${1:?BDI account id (first hex id in the console URL)}"
bdi_environment_id="${2:?BDI environment id (second hex id in the console URL)}"
boomi_account_id="${3:?Boomi Platform account id, e.g. aug9-M3RGTZ}"
shift 3
bdi_token="$(gcloud secrets versions access latest --secret=KUMORI_BOOMI_BDI_API_TOKEN --project=kumori-404602)"
boomi_json="$(gcloud secrets versions access latest --secret=KUMORI_BOOMI_INTEGRATION_API_TOKEN --project=kumori-404602)"
boomi_line() { python3 -c 'import json,sys; m=json.loads(sys.argv[1]); print(eval(sys.argv[2]))' "$boomi_json" "$1"; }

umask 077
{
  echo "BDI_API_URL=https://api.rivery.io"
  echo "BDI_API_TOKEN=${bdi_token}"
  echo "BDI_ACCOUNT_ID=${bdi_account_id}"
  echo "BDI_ENVIRONMENT_ID=${bdi_environment_id}"
  echo "BOOMI_API_URL=$(boomi_line "m['api_url']")"
  echo "BOOMI_USERNAME=$(boomi_line "m['username']")"
  echo "BOOMI_API_TOKEN=$(boomi_line "m['tokens']['${boomi_account_id}']")"
  echo "BOOMI_ACCOUNT_ID=${boomi_account_id}"
  echo "BOOMI_VERIFY_SSL=true"
  for line in "$@"; do echo "$line"; done
} > .env
echo "wrote .env (BDI + Boomi ${boomi_account_id} from Secret Manager, mode 600)"
