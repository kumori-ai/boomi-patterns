#!/usr/bin/env python3
"""Exercises the WRITE side of the Boomi Platform API and the BDI API on objects this run creates, then cleans up.

    python3 checks/check_api_writes.py

Platform: pinned to the trial account (notes/ids.json, key trial_account); refuses any other. Every object it makes is named "[API TEST] ..."
and is the only thing it updates, deploys or deletes. A no-op process (Start -> Stop) is deployed to the account's
test environment, executed once on its cloud atom, read back (record, log, artifacts) and undeployed.
BDI: a throwaway "[API TEST]" environment (variables, dataframes), and a copy of an existing data flow (update,
disable/activate, variables, versions, one run, delete). The one run costs 0.5 BDU trial credits (MAX_RUNS caps it).

Never called, by design (listed in the output with the reason):
  - access: user roles, SSO, federation, installer tokens, BDI users/SCIM/tokens (the access-widening rule)
  - the live runtime: atom create/delete, purge, restart, Java upgrade/rollback, queues, node offboard,
    runtime/cloud properties, attaching the atom to another environment
  - features this account does not have: account groups, integration-pack publishing, branches, merge requests
Results: notes/api_coverage/<date>_writes.json (gitignored). Leftovers from a crashed run are cleaned on the next start.
"""
import json
import re
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_api_coverage import BDI, OUT, ROOT, bdi_ids, call, secret  # noqa: E402

ACCOUNT = json.loads((ROOT / 'notes' / 'ids.json').read_text())['trial_account']  # gitignored
TAG = '[API TEST]'
MAX_RUNS = 1
NOT_CALLED = {
    'access (user roles, SSO, federation, installer tokens)': (
        'AccountUserRole', 'AccountUserFederation', 'AccountSSOConfig', 'AccountGroupUserRole', 'InstallerToken'),
    'the live runtime': (
        'Atom', 'AtomPurge', 'RuntimeRestartRequest', 'JavaUpgrade', 'JavaRollback', 'ClearQueue', 'MoveQueueRequest',
        'NodeOffboard', 'RuntimeCloud', 'RuntimeProperties', 'RuntimeObservabilitySettings', 'AtomSecurityPolicies',
        'SharedWebServer', 'SharedServerInformation', 'EnvironmentAtomAttachment', 'ComponentAtomAttachment',
        'ProcessAtomAttachment', 'IntegrationPackAtomAttachment', 'CloudAttachmentProperties',
        'AccountCloudAttachmentProperties', 'AccountCloudAttachmentPropertiesDefault', 'AccountCloudAttachmentQuota',
        'ForkedExecutionProperties', 'cloudAttachmentSecretsConfiguration', 'refreshSecretsManager',
        'PersistedProcessProperties', 'AtomCounters', 'ChangeListenerStatus'),
    'features this account does not have': (
        'AccountGroup', 'AccountGroupAccount', 'AccountGroupIntegrationPack', 'PublisherIntegrationPack',
        'ReleaseIntegrationPack', 'IntegrationPackInstance', 'IntegrationPackEnvironmentAttachment', 'Branch',
        'MergeRequest'),
}
BDI_NOT_CALLED = {'access (users, SCIM, tokens)': ('/users', '/scim_provisioning', '/v1/token')}

results = []


def rec(op, code, body=None, ok=(200, 201, 202, 204)):
    good = code in ok
    note = '' if code in (200, 201, 202, 204) else ('expected refusal: ' if good else '') + str(body)[:300]
    results.append(dict(op=op, code=code, ok=good, note=note))
    return good


def xml_attr(xml, name):
    m = re.search(rf'\b{name}="([^"]+)"', xml or '')
    return m.group(1) if m else None


# ---------------------------------------------------------------- Platform
def platform():
    creds = json.loads(secret('KUMORI_BOOMI_INTEGRATION_API_TOKEN'))
    import base64
    auth = 'Basic ' + base64.b64encode(f"BOOMI_TOKEN.{creds['username']}:{creds['tokens'][ACCOUNT]}".encode()).decode()
    base = f"{creds['api_url'].rstrip('/')}/api/rest/v1/{ACCOUNT}"

    def j(path, body=None, method=None, base_url=True):
        return call((base if base_url else '') + path, auth, method or ('POST' if body is not None else 'GET'), body)

    def x(path, xml):  # Component speaks XML only
        import urllib.request
        import urllib.error
        time.sleep(0.25)
        req = urllib.request.Request(base + path, data=xml.encode(), method='POST', headers={
            'Accept': 'application/xml', 'Content-Type': 'application/xml', 'Authorization': auth})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read()[:300].decode(errors='ignore')

    def q(obj, prop, value, op='EQUALS'):
        _, body = j(f'/{obj}/query', {'QueryFilter': {'expression': {'operator': op, 'property': prop,
                                                                      'argument': [value]}}})
        return body.get('result', []) if isinstance(body, dict) else []

    def cleanup(label):  # anything tagged, from this run or a crashed one
        for row in q('ComponentMetadata', 'name', f'{TAG}%', 'LIKE'):
            if not row.get('deleted') and row.get('currentVersion'):
                rec(f'DELETE /ComponentMetadata/{{id}} ({label})', *j(f"/ComponentMetadata/{row['componentId']}",
                                                                      method='DELETE'))
        for row in q('Environment', 'name', f'{TAG}%', 'LIKE'):
            rec(f'DELETE /Environment/{{id}} ({label})', *j(f"/Environment/{row['id']}", method='DELETE'))
        for row in q('Role', 'name', f'{TAG}%', 'LIKE'):
            rec(f'DELETE /Role/{{id}} ({label})', *j(f"/Role/{row['id']}", method='DELETE'))
        for row in q('Folder', 'name', f'{TAG}%', 'LIKE'):
            if not row.get('deleted'):
                rec(f'DELETE /Folder/{{id}} ({label})', *j(f"/Folder/{row['id']}", method='DELETE'))

    _, acct = j(f'/Account/{ACCOUNT}')
    if not isinstance(acct, dict) or acct.get('accountId') != ACCOUNT:
        sys.exit(f'FAIL token does not reach {ACCOUNT}: {acct}')
    cleanup('leftover')
    root = next(f['id'] for f in q('Folder', 'name', 'aug9') if not f.get('parentId'))
    env_live = next(e for e in q('Environment', 'name', 'Kumori Test'))['id']  # the env the cloud atom serves
    atom = q('EnvironmentAtomAttachment', 'environmentId', env_live)[0]['atomId']
    stamp = time.strftime('%Y%m%d%H%M%S')
    deployment = package = None
    try:
        # Folder
        code, f = j('/Folder', {'name': f'{TAG} coverage', 'parentId': root})
        rec('POST /Folder', code, f)
        folder = f['id']
        rec('POST /Folder/{id}', *j(f'/Folder/{folder}', {'id': folder, 'name': f'{TAG} coverage {stamp}',
                                                           'parentId': root}))

        # Component: a process property, created, updated (version 2), diffed, renamed
        def prop_xml(value, cid=None):
            idattr = f' componentId="{cid}"' if cid else ''
            return (f'<bns:Component xmlns:bns="http://api.platform.boomi.com/"{idattr} name="{TAG} property" '
                    f'type="processproperty" folderId="{folder}"><bns:encryptedValues/>'
                    f'<bns:description>API coverage test</bns:description><bns:object><DefinedProcessProperties '
                    f'xmlns=""><definedProcessProperty key="{KEY}"><helpText/><label>API_TEST</label><type>string'
                    f'</type><defaultValue>{value}</defaultValue><allowedValues/><persisted>false</persisted>'
                    f'</definedProcessProperty></DefinedProcessProperties></bns:object></bns:Component>')
        KEY = str(uuid.uuid4())
        code, out = x('/Component', prop_xml(1))
        rec('POST /Component', code, out)
        prop = xml_attr(out, 'componentId')
        code, out = x(f'/Component/{prop}', prop_xml(2, prop))
        rec('POST /Component/{id}', code, out)
        code, diff = j('/ComponentDiffRequest', {'componentId': prop, 'sourceVersion': 1, 'targetVersion': 2})
        rec('POST /ComponentDiffRequest', code, diff)
        rec('POST /ComponentMetadata/{id}', *j(f'/ComponentMetadata/{prop}',
                                               {'componentId': prop, 'name': f'{TAG} property renamed'}))

        # A no-op process: Start -> Stop
        proc_xml = (f'<bns:Component xmlns:bns="http://api.platform.boomi.com/" name="{TAG} no-op process" '
                    f'type="process" folderId="{folder}"><bns:encryptedValues/><bns:description>API coverage test'
                    f'</bns:description><bns:object><process xmlns="" allowSimultaneous="false" enableUserLog="false"'
                    f' processLogOnErrorOnly="false" purgeDataImmediately="false" updateRunDates="false" '
                    f'workload="general"><shapes><shape image="start" name="shape1" shapetype="start" userlabel="" '
                    f'x="96.0" y="94.0"><configuration><noaction/></configuration><dragpoints><dragpoint '
                    f'name="shape1.dragpoint1" toShape="shape2" x="231.0" y="106.0"/></dragpoints></shape><shape '
                    f'image="stop_icon" name="shape2" shapetype="stop" userlabel="" x="256.0" y="96.0"><configuration>'
                    f'<stop continue="true"/></configuration><dragpoints/></shape></shapes></process></bns:object>'
                    f'</bns:Component>')
        code, out = x('/Component', proc_xml)
        rec('POST /Component (process)', code, out)
        proc = xml_attr(out, 'componentId')

        # Environment of our own: create, rename, extensions, role scope, attachments
        code, e = j('/Environment', {'name': f'{TAG} env', 'classification': 'TEST'})
        rec('POST /Environment', code, e)
        env = e['id']
        rec('POST /Environment/{id}', *j(f'/Environment/{env}', {'id': env, 'name': f'{TAG} env {stamp}'}))
        rec('POST /EnvironmentExtensions/{id}', *j(f'/EnvironmentExtensions/{env}',
                                                   {'environmentId': env, 'id': env, 'partial': True}))
        role_ro = next(r for r in q('Role', 'name', 'Full Read Only'))['id']
        code, er = j('/EnvironmentRole', {'environmentId': env, 'roleId': role_ro})
        if rec('POST /EnvironmentRole', code, er):
            rec('DELETE /EnvironmentRole/{id}', *j(f"/EnvironmentRole/{er['id']}", method='DELETE'))
        code, ca = j('/ComponentEnvironmentAttachment', {'componentId': prop, 'environmentId': env})
        if code == 400 and 'cannot be attached' in str(ca):
            results.append(dict(op='POST /ComponentEnvironmentAttachment', code=400,
                                note='refused as expected: processproperty components cannot be attached'))
        elif rec('POST /ComponentEnvironmentAttachment', code, ca):
            rec('DELETE /ComponentEnvironmentAttachment/{id}', *j(f"/ComponentEnvironmentAttachment/{ca['id']}",
                                                                  method='DELETE'))
        code, pa = j('/ProcessEnvironmentAttachment', {'processId': proc, 'environmentId': env})
        if rec('POST /ProcessEnvironmentAttachment', code, pa):
            rec('DELETE /ProcessEnvironmentAttachment/{id}', *j(f"/ProcessEnvironmentAttachment/{pa['id']}",
                                                                method='DELETE'))

        # Package, deploy to the live test env, schedule off, execute once, read the evidence, undeploy
        code, p = j('/PackagedComponent', {'componentId': proc, 'packageVersion': f'api-test-{stamp}',
                                            'notes': TAG})
        rec('POST /PackagedComponent', code, p)
        package = p.get('packageId') if isinstance(p, dict) else None
        code, d = j('/DeployedPackage', {'environmentId': env_live, 'packageId': package, 'notes': TAG})
        rec('POST /DeployedPackage', code, d)
        deployment = d.get('deploymentId') if isinstance(d, dict) else None
        sched = q('ProcessSchedules', 'processId', proc)
        sched = [s for s in sched if s.get('atomId') == atom]
        if sched:
            rec('POST /ProcessSchedules/{id}', *j(f"/ProcessSchedules/{sched[0]['id']}",
                                                  {'id': sched[0]['id'], 'processId': proc, 'atomId': atom,
                                                   'Schedule': []}))
        status = [s for s in q('ProcessScheduleStatus', 'processId', proc) if s.get('atomId') == atom]
        if status:
            rec('POST /ProcessScheduleStatus/{id}', *j(f"/ProcessScheduleStatus/{status[0]['id']}",
                                                       {'id': status[0]['id'], 'processId': proc, 'atomId': atom,
                                                        'enabled': False}))
        time.sleep(5)  # the atom picks up a new deployment within seconds
        code, ex = j('/ExecutionRequest', {'atomId': atom, 'processId': proc})
        rec('POST /ExecutionRequest', code, ex)
        req_id = ex.get('requestId') if isinstance(ex, dict) else None
        execution = None
        for _ in range(30):
            if not req_id:
                break
            code, er = j(f'/ExecutionRecord/async/{req_id}')
            rows = er.get('result', []) if isinstance(er, dict) else []
            if code == 200 and rows and rows[0].get('status') not in ('INPROCESS', 'STARTED', 'PENDING'):
                execution = rows[0]
                break
            time.sleep(2)
        rec('GET /ExecutionRecord/async/{id}', 200 if execution else code,
            f"status {execution['status']}" if execution else er)
        if execution:
            eid = execution['executionId']
            for op, body in (('/ProcessLog', {'executionId': eid, 'logLevel': 'ALL'}),
                             ('/ExecutionArtifacts', {'executionId': eid})):
                for _ in range(12):  # the record answers before the logs are indexed
                    code, out = j(op, body)
                    if code != 400 or 'is invalid' not in str(out):
                        break
                    time.sleep(5)
                rec(f'POST {op}', code, out)
            rec('POST /ExecutionConnector/query', *j('/ExecutionConnector/query', {'QueryFilter': {'expression': {
                'operator': 'EQUALS', 'property': 'executionId', 'argument': [eid]}}}))
        code, out = j('/AtomLog', {'atomId': atom, 'logDate': date.today().isoformat()})
        if code == 400 and 'Bad Container' in str(out):
            results.append(dict(op='POST /AtomLog', code=400,
                                note='refused as expected: AtomLog is for self-hosted atoms, this one is Boomi-hosted'))
        else:
            rec('POST /AtomLog', code, out)

        # A role with no users: create, update, delete
        privs = {'@type': 'Privileges', 'Privilege': [{'@type': 'Privilege', 'name': 'ENV_VIEW'}]}
        code, r = j('/Role', {'@type': 'Role', 'accountId': ACCOUNT, 'name': f'{TAG} role',
                              'Description': 'API coverage test',
                              'Privileges': privs})
        if rec('POST /Role', code, r):
            rec('POST /Role/{id}', *j(f"/Role/{r['id']}", {'@type': 'Role', 'accountId': ACCOUNT, 'id': r['id'],
                                                           'name': f'{TAG} role',
                                                           'Description': 'updated', 'Privileges': privs}))
            rec('DELETE /Role/{id}', *j(f"/Role/{r['id']}", method='DELETE'))

        code, lic = j('/ConnectionLicensingReport', {})
        pending = re.search(r'https://\S+', str(lic)) if code == 400 else None
        if pending:  # an earlier request was never downloaded; Boomi refuses a new one until it is
            rec('GET ConnectionLicensingReport download (earlier request)', *j(pending.group(0).rstrip('".}'),
                method='GET', base_url=False))
            code, lic = j('/ConnectionLicensingReport', {})
        rec('POST /ConnectionLicensingReport', code, lic)
        if isinstance(lic, dict) and lic.get('url'):
            rec('GET ConnectionLicensingReport download', *j(lic['url'], method='GET', base_url=False))
    finally:
        if deployment:
            rec('DELETE /DeployedPackage/{id}', *j(f'/DeployedPackage/{deployment}', method='DELETE'))
        if package:
            rec('DELETE /PackagedComponent/{id}', *j(f'/PackagedComponent/{package}', method='DELETE'),
                ok=(200, 204, 404))
        cleanup('this run')


# ---------------------------------------------------------------- BDI
def bdi():
    auth = 'Bearer ' + secret('KUMORI_BOOMI_BDI_API_TOKEN')
    acc, env_main = bdi_ids()
    accb = f'{BDI}/v1/accounts/{acc}'

    def j(url, body=None, method=None):
        return call(url, auth, method or ('POST' if body is not None else 'GET'), body)

    E = '/v1/accounts/{account_id}/environments'
    R = E + '/{environment_id}/rivers/{river_cross_id}'
    mb = f'{accb}/environments/{env_main}'

    def settle(resp, label):
        """Wait for a BDI long-running operation (disable/activate) to finish; they return 202 and run async."""
        op_id = resp.get('operation_id') if isinstance(resp, dict) else None
        for _ in range(30):
            if not op_id:
                return
            code, op = j(f'{mb}/operations/{op_id}')
            if code == 200 and op.get('status') not in ('W', 'R', 'P'):
                results.append(dict(op=f'GET {E}/{{environment_id}}/operations/{{operation_id}} ({label})',
                                    code=200, note=f"status {op.get('status')}"))
                return
            time.sleep(3)

    def remove_river(cross_id, label):
        code, resp = j(f'{mb}/rivers/{cross_id}/disable_river', {})
        settle(resp, 'disable before delete')
        for _ in range(12):
            code, resp = j(f'{mb}/rivers/{cross_id}', method='DELETE')
            if code in (200, 204):
                break
            time.sleep(10)
        rec(f'DELETE {R} ({label})', code, resp)

    _, envs = j(f'{accb}/environments')
    for e in envs.get('items', []) if isinstance(envs, dict) else []:
        if str(e.get('environment_name', '')).startswith(TAG):
            rec(f'DELETE {E}/{{environment_id}} (leftover)', *j(f"{accb}/environments/{e['_id']}", method='DELETE'))
    _, rivers = j(f'{mb}/rivers')
    rows = rivers.get('items', []) if isinstance(rivers, dict) else []
    for r in rows:
        if r['name'].startswith(TAG):
            remove_river(r['river_cross_id'], 'leftover')
    rows = [r for r in rows if not r['name'].startswith(TAG)]
    test_env = copy = None
    runs = 0
    try:
        # A throwaway environment: rename, variables, dataframes. Never Production: its variables drive real flows.
        code, e = j(f'{accb}/environments', {'name': f'{TAG} env', 'description': 'API coverage test'})
        rec(f'POST {E}', code, e)
        test_env = (e.get('_id') or e.get('cross_id') or e.get('id')) if isinstance(e, dict) and code == 200 else None
        if not test_env:
            for op in (f'PUT {E}/{{environment_id}}', 'environment variables (PUT/GET/DELETE)', 'dataframes (6 ops)'):
                results.append(dict(op=op, code=None, note='no fixture: BDI trial is at its environment cap'))
        else:
            eb = f'{accb}/environments/{test_env}'
            rec(f'PUT {E}/{{environment_id}}', *j(eb, {'environment_name': f'{TAG} env renamed'}, 'PUT'))
            rec(f'PUT {E}/{{environment_id}}/variables', *j(f'{eb}/variables', {'variables': {'API_TEST': '1'}}, 'PUT'))
            rec(f'GET {E}/{{environment_id}}/variables', *j(f'{eb}/variables'))
            rec(f'DELETE {E}/{{environment_id}}/variables', *j(f'{eb}/variables?variable_key=API_TEST', method='DELETE'))
            df = 'api_test_df'
            if rec(f'POST {E}/{{environment_id}}/dataframes', *j(f'{eb}/dataframes', {'name': df})):
                d = f'{E}/{{environment_id}}/dataframes/{{dataframe_name}}'
                rec(f'PUT {d}', *j(f'{eb}/dataframes/{df}', {}, 'PUT'))
                rec(f'GET {d}', *j(f'{eb}/dataframes/{df}'))
                rec(f'GET {d}/download', *j(f'{eb}/dataframes/{df}/download'))
                rec(f'POST {d}/clear', *j(f'{eb}/dataframes/{df}/clear', {}))
                rec(f'DELETE {d}', *j(f'{eb}/dataframes/{df}', method='DELETE'))

        # Data flow lifecycle on a copy of an existing one (the lane-status flow has no schedule)
        src = next((r for r in rows if 'lane' in r['name'].lower()), rows[0] if rows else None)
        if src:
            code, c = j(f"{mb}/rivers/{src['river_cross_id']}/copy", {})
            rec(f'POST {R}/copy', code, c)
            copy = (c.get('river_cross_id') or c.get('cross_id')) if isinstance(c, dict) else None
        if copy:
            rb = f'{mb}/rivers/{copy}'
            _, river = j(rb)
            river = {k: v for k, v in river.items() if k not in ('cross_id', 'river_cross_id', 'account_id',
                                                                  'environment_id')}
            river['name'] = f'{TAG} copy of {src["name"]}'
            rec(f'PUT {R}', *j(rb, river, 'PUT'))
            code, resp = j(f'{rb}/disable_river', {})
            rec(f'POST {R}/disable_river', code, resp)
            settle(resp, 'disable')
            code, resp = j(f'{rb}/activate_river', {})
            rec(f'POST {R}/activate_river', code, resp)
            settle(resp, 'activate')
            rec(f'PUT {R}/variables', *j(f'{rb}/variables', {'items': []}, 'PUT'))
            if runs < MAX_RUNS:
                code, run = j(f'{rb}/run', {})
                rec(f'POST {R}/run', code, run)
                if code in (200, 202):
                    runs += 1
                    done = None
                    for _ in range(40):  # the run must finish before the copy can be disabled and deleted
                        now = datetime.now(timezone.utc)
                        w = urlencode({'start_time': (now - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S'),
                                       'end_time': now.strftime('%Y-%m-%dT%H:%M:%S')})
                        _, rl = j(f'{rb}/runs?{w}')
                        items = rl.get('items', []) if isinstance(rl, dict) else []
                        if items and items[0].get('status') in ('succeeded', 'failed', 'canceled'):
                            done = items[0]
                            break
                        time.sleep(5)
                    rec(f'GET {R}/runs (run finished)', 200 if done else 0,
                        f"{done['status']}, {done['units']} units" if done else 'run did not finish in 200s')
                    if done:  # it already finished, so a refusal is the right answer
                        rec(f'POST {R}/cancel_run', *j(f'{rb}/cancel_run', {'run_id': done['run_id']}),
                            ok=(200, 202, 204, 400, 409))
                    with open(ROOT / 'notes' / 'credits.md', 'a') as fh:
                        fh.write(f"| {date.today()} | {TAG} copy of {src['name']} (check_api_writes) | "
                                 f"{done['run_id'] if done else '?'} | "
                                 f"{str(done['units']) + ' (measured)' if done else '0.5 expected, unconfirmed'} | |\n")
    finally:
        if copy:
            remove_river(copy, 'this run')
        if test_env:
            rec(f'DELETE {E}/{{environment_id}}', *j(f'{accb}/environments/{test_env}', method='DELETE'))
    return runs


def main():
    started = time.time()
    runs = 0
    for half in (platform, bdi):  # one half failing must not lose the other's results
        try:
            runs = half() or runs
        except Exception as e:
            rec(f'{half.__name__} aborted', 0, repr(e))
    ok = [r for r in results if r.get('ok') or r['note'].startswith('refused as expected')]
    print(f'Write operations called: {len(results)}  answered OK: {len(ok)}  BDI runs: {runs} (cap {MAX_RUNS})')
    for r in results:
        if r not in ok:
            print(f"  {r['code']}  {r['op']}  {r['note'][:120]}")
    print('\nNever called, by design:')
    for why, objs in {**NOT_CALLED, **BDI_NOT_CALLED}.items():
        print(f'  {why}: {", ".join(objs)}')
    (OUT / f'{date.today().isoformat()}_writes.json').write_text(json.dumps(results, indent=1))
    if not ok:
        sys.exit('FAIL zero successful write calls: the verdict is meaningless')
    print(f'\nas of {date.today()}: {len(ok)} write operations answered OK on {ACCOUNT} and BDI, '
          f'in {time.time() - started:.0f}s; cleanup ran (see DELETE rows).')


if __name__ == '__main__':
    main()
