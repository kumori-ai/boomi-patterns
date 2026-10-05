#!/usr/bin/env python3
"""Proves the Flow -> Integration -> BDI bridge end to end, one link at a time, and prints a dated result.

    python3 checks/check_bdi_bridge.py

1. Listener auth: GET without credentials must be 401 (a 200 would mean the listener is open).
2. Integration -> BDI: GET with the listener login returns the BDI rivers list.
3. kumori.ai -> Integration: /api/boomi/flows (the "Run it live" button) answers live with the same rivers.
4. Flow -> Integration: run the Kumori BDI Monitor flow headlessly and load its table through the OpenAPI connector.
Every link must return the same river names. Zero rivers is an error, never a pass: an empty list proves nothing.
Read-only: listing rivers runs nothing in BDI and spends no credits. Credentials come from kumori-404602 Secret Manager.
"""
import json
import subprocess
import sys
import time
from datetime import date

LISTENER = 'https://boomi.kumori.ai/ws/simple/getListFlows'
KUMORI = 'https://kumori.ai/api/boomi/flows'
ACCOUNT = '1979-44C86S'
TENANT = 'c0bdf205-0a20-4865-8a4e-5bb408d5ba0b'
FLOW = '0438716c-4fa5-447c-9779-4a93924aa80b'
TABLE = 'BDI flows'


def secret(name):
    return json.loads(subprocess.run(['gcloud', 'secrets', 'versions', 'access', 'latest', f'--secret={name}',
                                      '--project=kumori-404602'], capture_output=True, text=True, check=True).stdout)


def curl(url, *args, body=None):
    cmd = ['curl', '-s', '-m', '60', '-w', '\n%{http_code} %{time_total}', *args]
    if body is not None:
        cmd += ['-H', 'Content-Type: application/json', '-d', '@-']
    out = subprocess.run(cmd + [url], input=json.dumps(body) if body is not None else None,
                         capture_output=True, text=True).stdout
    text, tail = out.rsplit('\n', 1)
    code, secs = tail.split()
    return code, text, int(float(secs) * 1000)


def fail(msg):
    sys.exit(f'FAIL {msg}')


def main():
    results = []
    code, _, _ = curl(LISTENER)
    if code != '401':
        fail(f'listener without credentials answered {code}, expected 401')
    results.append('listener refuses anonymous (401)')

    login = secret('KUMORI_BOOMI_INTEGRATION_LISTENER')[ACCOUNT]
    code, text, ms = curl(LISTENER, '-u', f"{login['username']}:{login['token']}")
    if code != '200':
        fail(f'listener with credentials answered {code}')
    names = sorted(r['name'] for r in json.loads(text).get('items') or [])
    if not names:
        fail('listener returned zero rivers; the check proves nothing on an empty list')
    results.append(f'Integration -> BDI: {len(names)} rivers in {ms} ms')

    code, text, ms = curl(KUMORI)
    body = json.loads(text)
    if code != '200' or not body.get('live'):
        fail(f'kumori.ai answered {code}: {body.get("error")}')
    if sorted(f['name'] for f in body['flows']) != names:
        fail('kumori.ai rivers differ from the listener')
    results.append(f'kumori.ai -> Integration: live, {body.get("elapsed_ms")} ms upstream')

    keys = secret('KUMORI_BOOMI_FLOW_API_KEY')
    hdr = ['-H', f"x-boomi-flow-api-key: {keys['keys'][TENANT]}", '-H', f'manywhotenant: {TENANT}', '-X', 'POST']
    api = keys['api_url']
    t0 = time.monotonic()
    code, text, _ = curl(f'{api}/api/run/1/state', *hdr, body={'id': FLOW})
    if code != '200':
        fail(f'Flow run init answered {code}: {text[:200]}')
    state = json.loads(text)
    sid, token = state['stateId'], state['stateToken']
    code, text, _ = curl(f'{api}/api/run/1/state/{sid}', *hdr, body={
        'stateId': sid, 'stateToken': token, 'currentMapElementId': state.get('currentMapElementId'),
        'invokeType': 'FORWARD', 'mapElementInvokeRequest': {'selectedOutcomeId': None}})
    if code != '200':
        fail(f'Flow forward answered {code}: {text[:200]}')
    run = json.loads(text)
    page = (run.get('mapElementInvokeResponses') or [{}])[0].get('pageResponse') or {}
    table = next((c for c in page.get('pageComponentResponses') or [] if c.get('developerName') == TABLE), None)
    if not table:
        fail(f'Flow page has no {TABLE!r} table')
    req = next(d for d in page['pageComponentDataResponses'] if d['pageComponentId'] == table['id'])['objectDataRequest']
    req['token'] = run.get('stateToken')
    code, text, _ = curl(f'{api}/api/run/1/service/data', *hdr, body=req)
    if code != '200':
        fail(f'Flow table load answered {code}: {text[:200]}')
    flow_names = sorted(next(p['contentValue'] for p in r['properties'] if p['developerName'] == 'name')
                        for r in json.loads(text).get('objectData') or [])
    if flow_names != names:
        fail(f'Flow table rivers differ from the listener: {flow_names}')
    results.append(f'Flow -> Integration: table loaded {len(flow_names)} rivers, run took {int((time.monotonic() - t0) * 1000)} ms')

    print(f'PASS as of {date.today().isoformat()}')
    for r in results:
        print(f'  {r}')
    print(f'  rivers: {", ".join(names)}')


if __name__ == '__main__':
    main()
