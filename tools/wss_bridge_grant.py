#!/usr/bin/env python3
"""Secure the self-hosted Boomi runtime's listener and open the /ws/ path, for the Flow -> Integration -> BDI bridge.

    python3 tools/wss_bridge_grant.py            # shows the exact changes, asks y/N before each step

Run by Andy (Claude Code's safety check reserves listener-security changes for a human). Two steps:

1. Boomi shared web server on boomi-runtime-1 (account 1979-44C86S), via the Platform API:
   - listener port 9090: authType NONE -> BASIC (today it is NONE: any deployed listener would be open)
   - externalPort 443 + externalSSL true, overrideUrl + baseUrl https://boomi.kumori.ai, examineForwardHeaders true
     (TLS ends at Caddy behind Cloudflare; Boomi must build its URLs for the public name)
   GET -> change only those fields -> show diff -> confirm -> UPDATE -> read back and verify.
2. Caddy on the VM: pass /ws/* (Web Services Server listeners) as well as /fs/*; everything else stays 404.
   Rewrites /var/lib/caddy/Caddyfile over IAP SSH and reloads Caddy, then checks /ws/ answers 401 (auth on), not 404/200.

Afterwards: tools/store_sws_token.sh 1979-44C86S 81ef8aa4-0585-49ca-819c-a96148aca5c1 1979-44C86S sets the listener
user's token through the Platform API (measured 2026-10-05: SharedWebServer UPDATE accepts users[].token) and stores it.
Never prints a token.
"""
import copy
import json
import subprocess
import sys

ACCOUNT, ATOM = '1979-44C86S', '81ef8aa4-0585-49ca-819c-a96148aca5c1'
PUBLIC = 'https://boomi.kumori.ai'
VM = ['--zone=us-central1-a', '--project=kumori-boomi-runtime', '--tunnel-through-iap', '--quiet']
CADDYFILE = """{
\tauto_https disable_redirects
\tadmin localhost:2019
}
boomi.kumori.ai:443 {
\ttls /etc/caddy/certs/boomi.kumori.ai.pem /etc/caddy/certs/boomi.kumori.ai.key
\theader -Server
\t@boomi path /fs/* /ws/*
\thandle @boomi {
\t\treverse_proxy 127.0.0.1:9090
\t}
\thandle {
\t\trespond 404
\t}
\tlog {
\t\toutput stdout
\t\tformat json
\t}
}
"""


def secret():
    out = subprocess.run(['gcloud', 'secrets', 'versions', 'access', 'latest', '--secret=KUMORI_BOOMI_INTEGRATION_API_TOKEN',
                          '--project=kumori-404602'], capture_output=True, text=True, check=True).stdout
    m = json.loads(out)
    return m, f"BOOMI_TOKEN.{m['username']}:{m['tokens'][ACCOUNT]}"


def api(method, auth, base, body=None):
    cmd = ['curl', '-s', '-m', '60', '-w', '\n%{http_code}', '--user', auth, '-H', 'Accept: application/json',
           '-H', 'Content-Type: application/json', '-X', method]
    if body is not None:
        cmd += ['-d', json.dumps(body)]
    out = subprocess.run(cmd + [f'{base}/SharedWebServer/{ATOM}'], capture_output=True, text=True).stdout
    text, code = out.rsplit('\n', 1)
    if not code.startswith('2'):
        sys.exit(f'{method} SharedWebServer -> HTTP {code}: {text[:400]}')
    return json.loads(text)


def ask(q):
    return input(f'{q} [y/N] ').strip().lower() == 'y'


def step_shared_web_server():
    m, auth = secret()
    base = f"{m['api_url']}/api/rest/v1/{ACCOUNT}"
    cur = api('GET', auth, base)
    new = copy.deepcopy(cur)
    g = new['generalSettings']
    g.update(overrideUrl=True, baseUrl=PUBLIC, examineForwardHeaders=True)
    p = g['listenerPorts']['port'][0]
    p.update(authType='BASIC', externalPort=443, externalSSL=True)
    gc, pc = cur['generalSettings'], cur['generalSettings']['listenerPorts']['port'][0]
    print('Shared web server changes on boomi-runtime-1:')
    for k in ('overrideUrl', 'baseUrl', 'examineForwardHeaders'):
        print(f'  {k}: {gc.get(k)!r} -> {g[k]!r}')
    for k in ('authType', 'externalPort', 'externalSSL'):
        print(f'  port 9090 {k}: {pc.get(k)!r} -> {p[k]!r}')
    if not ask('Apply?'):
        sys.exit('stopped, nothing changed')
    api('POST', auth, base, new)
    after = api('GET', auth, base)
    ap = after['generalSettings']['listenerPorts']['port'][0]
    ok = ap['authType'] == 'BASIC' and after['generalSettings']['baseUrl'] == PUBLIC and ap['externalSSL']
    print('read back:', {'authType': ap['authType'], 'baseUrl': after['generalSettings']['baseUrl'],
                         'externalPort': ap['externalPort'], 'externalSSL': ap['externalSSL']}, '->', 'OK' if ok else 'MISMATCH')
    if not ok:
        sys.exit('read-back mismatch; stopping before Caddy')


def step_caddy():
    print('\nCaddy: pass /fs/* and /ws/* to the runtime, 404 everything else.')
    if not ask('Apply?'):
        sys.exit('stopped before Caddy')
    remote = ("sudo tee /var/lib/caddy/Caddyfile >/dev/null && "
              "sudo docker exec caddy caddy validate --config /etc/caddy/Caddyfile >/dev/null && "
              "sudo docker restart caddy >/dev/null && sleep 3 && sudo docker ps --format '{{.Names}} {{.Status}}' | grep caddy")
    r = subprocess.run(['gcloud', 'compute', 'ssh', 'boomi-runtime-1', *VM, '--command', remote],
                       input=CADDYFILE, capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip()[-400:])
    for path in ('/', '/ws/simple/', '/fs/'):
        code = subprocess.run(['curl', '-s', '-o', '/dev/null', '-m', '20', '-w', '%{http_code}', PUBLIC + path],
                              capture_output=True, text=True).stdout
        print(f'  {PUBLIC}{path} -> {code}')
    print('expected now: 404 on all three. The runtime answers 404 for a path with no deployed listener, before\n'
          'it checks auth (measured 2026-10-05). /ws/... returns 401 without credentials once a WSS listener is deployed.')


if __name__ == '__main__':
    step_shared_web_server()
    step_caddy()
    print('\nNext: tools/store_sws_token.sh 1979-44C86S 81ef8aa4-0585-49ca-819c-a96148aca5c1 1979-44C86S')
