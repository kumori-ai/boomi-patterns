#!/usr/bin/env bash
# Rotates a Boomi runtime shared web server user's token through the Platform API and stores it, no console step.
# Measured 2026-10-05: SharedWebServer UPDATE accepts userManagement.users[].token (GET never returns it).
# Order: set the new token on the runtime, wait until a deployed listener answers 200 with it, then add it to
# KUMORI_BOOMI_INTEGRATION_LISTENER ({accountId: {"username", "token"}}) and disable + destroy the old version.
# The token never touches stdout or disk outside a mode-600 temp file.
# Usage: tools/store_sws_token.sh <account_id> <runtime_id> <sws_username> [listener_url]
#   e.g. tools/store_sws_token.sh 1979-44C86S 81ef8aa4-0585-49ca-819c-a96148aca5c1 1979-44C86S
#   listener_url defaults to https://boomi.kumori.ai/ws/simple/getListFlows (must be deployed and auth-protected)
set -euo pipefail
umask 077
python3 - "$@" <<'EOF'
import copy, json, os, secrets, subprocess, sys, tempfile, time
account, runtime, user = sys.argv[1:4]
listener = sys.argv[4] if len(sys.argv) > 4 else 'https://boomi.kumori.ai/ws/simple/getListFlows'
P, API, LIS = 'kumori-404602', 'KUMORI_BOOMI_INTEGRATION_API_TOKEN', 'KUMORI_BOOMI_INTEGRATION_LISTENER'

def secret(name):
    return json.loads(subprocess.run(['gcloud', 'secrets', 'versions', 'access', 'latest', f'--secret={name}', f'--project={P}'],
                                     capture_output=True, text=True, check=True).stdout)

a = secret(API)
auth = f"BOOMI_TOKEN.{a['username']}:{a['tokens'][account]}"
url = f"{a['api_url']}/api/rest/v1/{account}/SharedWebServer/{runtime}"

def call(method, body=None):
    cmd = ['curl', '-s', '-m', '60', '-w', '\n%{http_code}', '--user', auth, '-H', 'Accept: application/json',
           '-H', 'Content-Type: application/json', '-X', method]
    if body is not None:
        cmd += ['-d', '@-']
    out = subprocess.run(cmd + [url], input=json.dumps(body) if body is not None else None, capture_output=True, text=True).stdout
    text, code = out.rsplit('\n', 1)
    return code, text

code, text = call('GET')
if code != '200':
    sys.exit(f'GET SharedWebServer -> HTTP {code}')
new = copy.deepcopy(json.loads(text))
users = [u for u in new['userManagement']['users'] if u['username'] == user]
if not users:
    sys.exit(f'no shared web server user {user!r} on runtime {runtime}; nothing changed')
tok = secrets.token_urlsafe(32)
users[0]['token'] = tok
code, text = call('POST', new)
if code != '200':
    sys.exit(f'UPDATE SharedWebServer -> HTTP {code}: {text.replace(tok, "<token>")[:300]}')

status = '?'
for _ in range(9):
    time.sleep(10)
    status = subprocess.run(['curl', '-s', '-o', '/dev/null', '-m', '30', '-w', '%{http_code}', '-u', f'{user}:{tok}', listener],
                            capture_output=True, text=True).stdout
    if status == '200':
        break
if status != '200':
    sys.exit(f'runtime has the new token but {listener} answered {status}; secret NOT updated, rerun once the listener is up')

m = secret(LIS)
m[account] = {'username': user, 'token': tok}
prev = subprocess.run(['gcloud', 'secrets', 'versions', 'list', LIS, f'--project={P}', '--filter=state=enabled',
                       '--format=value(name)'], capture_output=True, text=True).stdout.split()
with tempfile.NamedTemporaryFile('w', delete=False) as f:
    json.dump(m, f)
try:
    subprocess.run(['gcloud', 'secrets', 'versions', 'add', LIS, f'--project={P}', f'--data-file={f.name}'], check=True, capture_output=True)
finally:
    os.remove(f.name)
for v in prev:
    for step in ('disable', 'destroy'):
        subprocess.run(['gcloud', 'secrets', 'versions', step, v, f'--secret={LIS}', f'--project={P}', '--quiet'], check=True, capture_output=True)
print(f'rotated listener token for {user} on {account}: runtime updated, {listener} -> 200, stored in {LIS}, destroyed {prev}')
EOF
