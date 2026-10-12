#!/usr/bin/env python3
"""Downloads the Boomi Platform API and BDI OpenAPI specs and calls every READ operation in them, so we know
which endpoints actually work on our accounts, not just which ones are documented.

    python3 checks/check_api_coverage.py [platform_account_id]

Read-only by construction: Platform `POST /<Object>/query`, `/queryMore`, `/bulk` (type GET) and every GET; BDI GETs.
Every other operation (create, update, delete, execute, run, restart, purge, provision) is listed as untested-write,
never called. BDI GETs spend no credits. Path ids are filled from the account's own query/list results; an id we
could not find is recorded as no-fixture, never as a pass. Zero successful calls is an error.

Specs land in notes/specs/ and the full per-operation result in notes/api_coverage/ (both gitignored: the Platform
spec and the results carry account, runtime and river ids). Credentials come from kumori-404602 Secret Manager.
"""
import base64
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / 'notes' / 'specs'
OUT = ROOT / 'notes' / 'api_coverage'
BDI = 'https://api.rivery.io'
PAUSE = 0.25


def secret(name):
    return subprocess.run(['gcloud', 'secrets', 'versions', 'access', 'latest', f'--secret={name}',
                           '--project=kumori-404602'], capture_output=True, text=True, check=True).stdout.strip()


def call(url, auth, method='GET', body=None, raw=False, accept='application/json'):
    time.sleep(PAUSE)
    data = body.encode() if raw else json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, method=method, data=data,
                                 headers={'Accept': accept, 'Authorization': auth,
                                          'Content-Type': 'text/plain' if raw else 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw) if raw else None
            except ValueError:
                return r.status, {'_non_json_bytes': len(raw)}
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:2000].decode(errors='ignore')  # long enough for Boomi's embedded URLs
    except Exception as e:  # timeouts, resets: recorded, not fatal
        return 0, str(e)[:300]


def operations(spec):
    for path, ops in spec['paths'].items():
        for method in ops:
            if method in ('get', 'post', 'put', 'patch', 'delete'):
                yield method.upper(), path


def first_id(obj, row):
    """A row's own id: '<object>Id' (executionId for ExecutionRecord), else 'id', else the first field ending in Id."""
    if not isinstance(row, dict):
        return None
    own = obj[0].lower() + obj[1:] + 'Id'
    for key in (own, 'executionId' if obj == 'ExecutionRecord' else None, 'id'):
        if key and isinstance(row.get(key), str) and row[key]:
            return row[key]
    return next((v for k, v in row.items() if k.endswith('Id') and isinstance(v, str) and v), None)


def flt(prop, value, op='EQUALS'):
    return {'QueryFilter': {'expression': {'operator': op, 'property': prop, 'argument': [value]}}}


# Queries Boomi refuses without a filter: object -> (property, fixture it comes from, operator)
FILTERS = {
    'AtomConnectionFieldExtensionSummary': ('atomId', 'Atom', 'EQUALS'),
    'EnvironmentConnectionFieldExtensionSummary': ('environmentId', 'Environment', 'EQUALS'),
    'EnvironmentExtensions': ('environmentId', 'Environment', 'EQUALS'),
    'EnvironmentMapExtensionsSummary': ('environmentId', 'Environment', 'EQUALS'),
    'EnvironmentMapExtensionExternalComponent': ('environmentMapExtensionId', 'EnvironmentMapExtension', 'EQUALS'),
    'EnvironmentMapExtensionUserDefinedFunctionSummary': ('environmentMapExtensionId', 'EnvironmentMapExtension', 'EQUALS'),
    'ExecutionConnector': ('executionId', 'ExecutionRecord', 'EQUALS'),
    'GenericConnectorRecord': ('executionId', 'ExecutionRecord', 'EQUALS'),
    'GlobalVariableUpdateTransaction': ('envId', 'Environment', 'EQUALS'),
    'GlobalVariableValue': ('envId', 'Environment', 'EQUALS'),
    'ComponentReference': ('componentId', 'ComponentMetadata', 'EQUALS'),
    'OrganizationComponent': ('name', '%', 'LIKE'),
    'SharedCommunicationChannelComponent': ('name', '%', 'LIKE'),
    'ListenerStatus': ('containerId', 'Atom', 'EQUALS'),
}
# Objects that exist only on a Boomi-hosted runtime cloud; a self-hosted atom is the wrong container
CLOUD_ONLY = ('AccountCloudAttachment', 'AtomDiskSpace', 'AtomSecurityPolicies', 'CloudAttachmentProperties',
              'ForkedExecutionProperties', 'Cloud', 'RuntimeCloud')
# Reads whose id only exists after a write (an execution, a diff, a merge): never faked
NEEDS_WRITE = {'ExecutionRecord/async': 'id comes from an ExecutionRequest (runs a process)',
               'ComponentDiffRequest': 'id comes from a component diff request (a POST)'}
COMPOUND = {'EnvironmentMapExtension': 'EnvironmentMapExtension', 'EnvironmentRole': 'EnvironmentRole',
            'EnvironmentProcessConfiguration': None}


# ---------------------------------------------------------------- Platform API
def platform(account):
    creds = json.loads(secret('KUMORI_BOOMI_INTEGRATION_API_TOKEN'))
    auth = 'Basic ' + base64.b64encode(f"BOOMI_TOKEN.{creds['username']}:{creds['tokens'][account]}".encode()).decode()
    base = f"{creds['api_url'].rstrip('/')}/api/rest/v1/{account}"
    code, spec = call(f'{base}/openapi.json', auth)
    if code != 200:
        sys.exit(f'FAIL Platform spec download answered {code}')
    (SPECS / f'platform_{account}.json').write_text(json.dumps(spec))
    ops = list(operations(spec))
    queried = {p.split('/')[-2] for _, p in ops if p.endswith('/query')}
    results, fixtures, tokens, async_tokens = [], {'Account': account}, {}, {}

    def pcall(url, method='GET', body=None, raw=False):
        code, out = call(url, auth, method, body, raw)
        if code in (406, 500) and 'Invalid media type' in str(out):  # Component speaks XML only
            code, out = call(url, auth, method, body, raw, accept='application/xml')
            return code, out, 'XML only (406 on JSON)'
        return code, out, ''

    def record(op, code, body, extra=''):
        note = extra if code in (200, 204) else f'{extra} {body}'.strip()
        results.append(dict(op=op, code=code, note=note))

    def run_query(path, obj, body):
        code, out, extra = pcall(base + path, 'POST', body)
        rows = out.get('result', []) if isinstance(out, dict) else []
        if rows and first_id(obj, rows[0]):
            fixtures.setdefault(obj, first_id(obj, rows[0]))
        if isinstance(out, dict) and out.get('queryToken'):
            tokens[obj] = out['queryToken']
        if isinstance(out, dict) and out.get('asyncToken'):
            async_tokens[obj] = out['asyncToken'].get('token')
        n = f"{out.get('numberOfResults', len(rows))} results" if isinstance(out, dict) and 'result' in out else ''
        return code, out, ' '.join(x for x in (extra, n) if x)

    pending = []
    for method, path in ops:  # pass 1: unfiltered queries, to learn ids
        if path.endswith('/query'):
            obj = path.split('/')[-2]
            if obj in FILTERS:
                pending.append((method, path, obj))
                continue
            code, out, note = run_query(path, obj, {})
            record(f'{method} {path}', code, out, note)
    for method, path, obj in pending:  # pass 1b: queries that need a filter built from pass 1
        prop, src, op = FILTERS[obj]
        value = src if src == '%' else fixtures.get(src)
        if not value:
            results.append(dict(op=f'{method} {path}', code=None, note=f'no fixture: needs a {src} id for {prop}'))
            continue
        code, out, note = run_query(path, obj, flt(prop, value, op))
        record(f'{method} {path}', code, out, f'filtered on {prop}. {note}'.strip())

    def fixture_for(obj):
        if obj.startswith(CLOUD_ONLY):
            return fixtures.get('Cloud')
        if obj in COMPOUND:
            return fixtures.get(COMPOUND[obj]) if COMPOUND[obj] else None
        if obj in fixtures:
            return fixtures[obj]
        if obj in queried:  # it has its own query; borrowing another object's id would test nothing
            return None
        for prefix, src in (('Account', 'Account'), ('Atom', 'Atom'), ('Runtime', 'Atom'), ('Listener', 'Atom'),
                            ('SharedWebServer', 'Atom'), ('Persisted', 'Atom'), ('ChangeListener', 'Atom'),
                            ('Environment', 'Environment'), ('Process', 'Process'), ('Component', 'ComponentMetadata'),
                            ('PackagedComponent', 'PackagedComponent'), ('DeployedPackage', 'DeployedPackage'),
                            ('IntegrationPack', 'IntegrationPack')):
            if obj.startswith(prefix) and src in fixtures:
                return fixtures[src]
        return None

    def missing(obj):
        if obj.startswith(CLOUD_ONLY):
            return 'no fixture: needs a Boomi-hosted runtime cloud (this account has a self-hosted atom only)'
        if obj in COMPOUND:
            return 'no fixture: needs a compound id'
        return 'no fixture id'

    for method, path in ops:  # pass 2: reads that need an id or a token
        parts = path.strip('/').split('/')
        obj = parts[1] if parts[0] == 'async' else parts[0]
        op = f'{method} {path}'
        if path.endswith('/query'):
            continue
        need = next((why for key, why in NEEDS_WRITE.items() if path.startswith('/' + key)), None)
        if need and method == 'GET':
            results.append(dict(op=op, code=None, note=f'no fixture: {need}'))
        elif path.endswith('/queryMore'):
            if obj not in tokens:
                results.append(dict(op=op, code=None, note='no fixture: query returned a single page'))
                continue
            code, out, extra = pcall(base + path, 'POST', tokens[obj], raw=True)  # the token is the whole body
            record(op, code, out, extra)
        elif path.endswith('/bulk'):
            fid = fixture_for(obj)
            if not fid:
                results.append(dict(op=op, code=None, note=missing(obj)))
                continue
            code, out, extra = pcall(base + path, 'POST', {'type': 'GET', 'request': [{'id': fid}]})
            record(op, code, out, extra)
        elif method == 'GET' and (path.endswith('/response/{token}') or path.endswith('/async/{id}')):
            tok = async_tokens.get(obj)
            if not tok and parts[0] == 'async':
                fid = fixture_for(obj)
                if not fid:
                    results.append(dict(op=op, code=None, note=missing(obj)))
                    continue
                code, out, _ = pcall(f'{base}/async/{obj}/{fid}')  # the GET that starts it
                tok = out.get('asyncToken', {}).get('token') if isinstance(out, dict) else None
                if not tok:
                    record(op, code, out, 'could not start the async request:')
                    continue
            if not tok:
                results.append(dict(op=op, code=None, note=missing(obj)))
                continue
            url = base + re.sub(r'\{\w+\}', tok, path)
            for _ in range(15):
                code, out, extra = pcall(url)
                if code != 202:
                    break
                time.sleep(1)
            record(op, code, out, extra)
        elif method == 'GET':
            url = base + path
            if re.search(r'\{\w+\}', path):
                fid = fixture_for(obj)
                if not fid:
                    results.append(dict(op=op, code=None, note=missing(obj)))
                    continue
                url = base + re.sub(r'\{\w+\}', fid, path)
            code, out, extra = pcall(url)
            record(op, code, out, extra)
        else:
            results.append(dict(op=op, code=None, note='untested-write'))
    return spec, results


# ---------------------------------------------------------------- BDI API
def bdi_ids():
    text = (ROOT / 'notes' / 'trial.md').read_text()
    acc = re.search(r'Account id:\s*([0-9a-f]{24})', text).group(1)
    env = re.search(r'Production\s+([0-9a-f]{24})', text).group(1)
    return acc, env


def bdi():
    auth = 'Bearer ' + secret('KUMORI_BOOMI_BDI_API_TOKEN')
    code, spec = call(f'{BDI}/openapi.json', auth)
    if code != 200:
        sys.exit(f'FAIL BDI spec download answered {code}')
    (SPECS / 'bdi.json').write_text(json.dumps(spec))
    acc, env = bdi_ids()
    env_base = f'{BDI}/v1/accounts/{acc}/environments/{env}'
    ids = {'account_id': acc, 'environment_id': env}
    now = datetime.now(timezone.utc).replace(microsecond=0)
    window = {'start_time': (now - timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%S'),
              'end_time': now.strftime('%Y-%m-%dT%H:%M:%S')}

    def query_for(path):
        """Values for every required query parameter: a 30-day window for times, the spec's own example otherwise."""
        q = {}
        for prm in spec['paths'][path]['get'].get('parameters', []):
            if prm.get('in') != 'query' or not prm.get('required'):
                continue
            name, schema = prm['name'], prm.get('schema', {})
            if name in window:
                q[name] = window[name]
            elif schema.get('examples') or prm.get('example'):
                q[name] = (schema.get('examples') or [prm.get('example')])[0]
            else:
                return None
        return q

    def url_for(path):
        q = query_for(path)
        if q is None:
            return None
        url = BDI + re.sub(r'\{(\w+)\}', lambda m: ids[m.group(1)], path)
        return url + ('?' + urllib.parse.urlencode(q) if q else '')

    def items(body):
        if isinstance(body, list):
            return body
        if isinstance(body, dict):
            return next((v for v in body.values() if isinstance(v, list)), [])
        return []

    def learn(path, key, *fields):  # fill one id from a list endpoint
        if any(p not in ids for p in re.findall(r'\{(\w+)\}', path)):
            return
        url = url_for(path)
        if not url:
            return
        _, body = call(url, auth)
        rows = items(body)
        for f in fields:
            if rows and isinstance(rows[0], dict) and rows[0].get(f):
                ids[key] = str(rows[0][f])
                return

    e, r = '/v1/accounts/{account_id}/environments/{environment_id}', '/rivers/{river_cross_id}'
    learn(e + '/rivers', 'river_cross_id', 'cross_id', 'river_cross_id', 'id')
    learn(e + r + '/runs', 'run_id', 'run_id', 'id')
    learn(e + r + '/versions', 'version_id', 'version_id', 'id')
    learn(e + r + '/activities_run_groups', 'run_group_id', 'run_group_id', 'id')
    learn(e + r + '/runs/{run_id}/logic_steps', 'step_id', 'step_id', 'id')
    learn('/v1/accounts/{account_id}/users', 'user_id', 'user_id', 'id', '_id')
    learn(e + '/audit_events', 'event_id', 'event_id', 'id', '_id')
    learn(e + '/dataframes', 'dataframe_name', 'name')
    learn('/v1/connections_types', 'connection_type', 'connection_type', 'name', 'id')

    results = []
    for method, path in operations(spec):
        op = f'{method} {path}'
        if method != 'GET':
            results.append(dict(op=op, code=None, note='untested-write'))
            continue
        gaps = [p for p in re.findall(r'\{(\w+)\}', path) if p not in ids]
        url = None if gaps else url_for(path)
        if not url:
            why = ', '.join(gaps) if gaps else 'a required query value with no example'
            results.append(dict(op=op, code=None, note=f'no fixture: {why}'))
            continue
        code, body = call(url, auth)
        results.append(dict(op=op, code=code, note='' if code == 200 else body))
    return spec, results


def summarize(name, results):
    tally = Counter('pass' if r['code'] in (200, 204) else 'async-accepted' if r['code'] == 202 else 'untested-write' if r['note'] == 'untested-write'
                    else 'no-fixture' if r['code'] is None else f"http {r['code']}" for r in results)
    print(f'\n{name}: {len(results)} operations  ' + '  '.join(f'{k} {v}' for k, v in sorted(tally.items())))
    for r in results:
        if r['code'] not in (200, 202, 204, None):
            print(f"  {r['code']}  {r['op']}  {str(r['note'])[:110]}")
    why = Counter(re.sub(r'\{.*', '', r['note']).strip() for r in results if r['code'] is None and r['note'] != 'untested-write')
    for reason, n in why.most_common():
        print(f'  untested x{n}: {reason}')
    return tally['pass'] + tally['async-accepted']


def main():
    account = sys.argv[1] if len(sys.argv) > 1 else json.loads((ROOT / 'notes' / 'ids.json').read_text())['boomi_account']  # gitignored
    SPECS.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.time()
    p_spec, p_results = platform(account)
    b_spec, b_results = bdi()
    passed = summarize(f"Platform API ({p_spec['info'].get('title')}, {account})", p_results)
    passed += summarize(f"BDI API ({b_spec['info'].get('title')})", b_results)
    stamp = date.today().isoformat()
    (OUT / f'{stamp}_{account}.json').write_text(json.dumps({'platform': p_results, 'bdi': b_results}, indent=1))
    if passed == 0:
        sys.exit('FAIL zero successful calls: the verdict is meaningless')
    print(f'\nas of {stamp}: {passed} read operations answered 200, in {time.time() - started:.0f}s. '
          f'Full results: notes/api_coverage/{stamp}_{account}.json')


if __name__ == '__main__':
    main()
