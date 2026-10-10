#!/usr/bin/env python3
"""Put boomi.kumori.ai behind Cloudflare for the self-hosted Boomi runtime (GCP kumori-boomi-runtime).

    ~/Desktop/code/kumori/venv_kumori/bin/python tools/cloudflare_boomi_origin.py

What it does, in the kumori.ai zone (kumoridotai Cloudflare account, via cloudflare_edge's API helper):
1. Creates A record boomi.kumori.ai -> the VM's address (notes/ids.json, key runtime_ip), PROXIED (orange cloud). Skips if it already exists.
2. Issues a Cloudflare Origin CA certificate for boomi.kumori.ai (ECC, 15 years) from a locally generated
   CSR. The private key never leaves this Mac until it is copied to the VM over IAP.
Writes the key + cert to OUT_DIR (mode 600). Prints only ids and dates.
Idempotent for the DNS record; issues a new certificate each run.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.expanduser('~/Desktop/code/_local_infrastructure/cloudflare_edge'))
import edge  # noqa: E402

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
HOST, IP = 'boomi.kumori.ai', json.load(open(os.path.join(REPO, 'notes', 'ids.json')))['runtime_ip']  # gitignored
OUT_DIR = os.path.join(REPO, '_oneoff', 'cf_origin')  # gitignored scratch


def main():
    os.makedirs(OUT_DIR, mode=0o700, exist_ok=True)
    os.umask(0o077)
    key, csr, pem = (os.path.join(OUT_DIR, f'{HOST}.{x}') for x in ('key', 'csr', 'pem'))
    subprocess.run(['openssl', 'req', '-new', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1', '-nodes',
                    '-keyout', key, '-out', csr, '-subj', f'/CN={HOST}'], check=True, capture_output=True)

    zone = edge.find_zone('kumori.ai')
    zid = zone['id']
    print(f"zone kumori.ai: {zone['status']}, ssl mode {edge._cf('GET', f'/zones/{zid}/settings/ssl')['value']}")

    have = edge._cf('GET', f'/zones/{zid}/dns_records?name={HOST}')
    if have:
        print('record exists:', [(r['type'], r['content'], 'proxied' if r['proxied'] else 'dns-only') for r in have])
    else:
        r = edge._cf('POST', f'/zones/{zid}/dns_records', type='A', name=HOST, content=IP, proxied=True, ttl=1,
                     comment='Boomi Integration runtime (GCP kumori-boomi-runtime), 2026-10-05')
        print('created', r['type'], r['name'], '->', r['content'], 'proxied' if r['proxied'] else 'dns-only')

    c = edge._cf('POST', '/certificates', hostnames=[HOST], requested_validity=5475, request_type='origin-ecc',
                 csr=open(csr).read())
    with open(pem, 'w') as f:
        f.write(c['certificate'])
    print(f"origin certificate {c['id']} for {HOST}, expires {c['expires_on']}; key + cert in {OUT_DIR}")


if __name__ == '__main__':
    main()
