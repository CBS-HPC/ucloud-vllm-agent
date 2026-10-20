from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from ucloud_vllm_agent import lifecycle
from ucloud_vllm_agent.config import load_json
from ucloud_vllm_agent.hosting import validate_profile
from ucloud_vllm_agent.state import Journal, operation_lock, save
from ucloud_vllm_agent.transport import register_web_route


class Client:
    def __init__(self):
        self.settings = SimpleNamespace(project='our-project', template_job_id='template')
        self.jobs = {}
        self.submissions = []
        self.terminated = []
        self.lost_response = False

    def submit_job(self, spec):
        self.submissions.append(deepcopy(spec))
        job_id = str(100 + len(self.submissions))
        self.jobs[job_id] = {'id': job_id, 'specification': deepcopy(spec),
                             'owner': {'project': 'our-project'}, 'updates': [{'state': 'RUNNING'}]}
        if self.lost_response:
            raise TimeoutError('private-credential-bearing-response')
        return {'responses': [{'id': job_id}]}

    def retrieve_job(self, job_id, **kwargs):
        return deepcopy(self.jobs[job_id])

    def terminate_job(self, job_id):
        self.terminated.append(job_id)
        self.jobs[job_id]['updates'].append({'state': 'SUCCESS'})

    def request(self, method, path, **kwargs):
        if path == '/api/ingresses/retrieve':
            return SimpleNamespace(json=lambda: {'specification': {'domain': 'test.example'},
                                                 'status': {'boundTo': []}})
        raise AssertionError('Unexpected request')


def test_acknowledgement_loss_cannot_create_a_second_job_after_process_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(lifecycle, 'CONTROL_ROOT', tmp_path / 'control')
    client = Client(); client.lost_response = True
    with pytest.raises(RuntimeError, match='unknown'):
        Journal(tmp_path).submitted('hosting', client, {'name': 'owned-attempt'})
    persisted = Journal(tmp_path)
    assert persisted.data['hosting_submission'] == 'unknown'
    assert 'private-credential' not in persisted.path.read_text()
    with pytest.raises(ValueError, match='unknown'):
        persisted.submitted('hosting', client, {'name': 'owned-attempt'})
    assert len(client.submissions) == 1
    lifecycle.reconcile(client, tmp_path, '101', 'hosting')
    assert Journal(tmp_path).submitted('hosting', client, {'name': 'owned-attempt'}) == '101'
    assert len(client.submissions) == 1


def test_reconciliation_rejects_an_unrelated_job(tmp_path, monkeypatch):
    monkeypatch.setattr(lifecycle, 'CONTROL_ROOT', tmp_path / 'control')
    client = Client()
    Journal(tmp_path).update('submission_unknown', hosting_submission='unknown', hosting_submission_name='ours')
    client.submit_job({'name': 'somebody-else'})
    with pytest.raises(ValueError, match='intent'):
        lifecycle.reconcile(client, tmp_path, '101', 'hosting')
    assert not Journal(tmp_path).data.get('hosting_job_id')


def test_operation_lock_rejects_concurrent_mutation_and_releases_on_error(tmp_path):
    lock = tmp_path / 'operation.lock'
    with pytest.raises(RuntimeError):
        with operation_lock(lock):
            with pytest.raises(ValueError, match='already running'):
                with operation_lock(lock):
                    pass
            raise RuntimeError('interrupted')
    with operation_lock(lock):
        pass


def test_release_targets_only_recorded_jobs_and_keeps_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(lifecycle, 'CONTROL_ROOT', tmp_path / 'control')
    client = Client()
    for name in ['owned-hosting', 'owned-preparation', 'operator-template']:
        client.submit_job({'name': name})
    journal = Journal(tmp_path)
    journal.update(hosting_job_id='101', hosting_submission_name='owned-hosting',
                   preparation_job_id='102', preparation_submission_name='owned-preparation')
    lifecycle.release(client, tmp_path)
    assert client.terminated == ['101', '102']
    assert client.retrieve_job('103')['updates'][-1]['state'] == 'RUNNING'
    assert journal.path.exists()
    assert Journal(tmp_path).data['state'] == 'released'


def test_release_refuses_ownership_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(lifecycle, 'CONTROL_ROOT', tmp_path / 'control')
    client = Client(); client.submit_job({'name': 'original'})
    Journal(tmp_path).update(hosting_job_id='101', hosting_submission_name='different')
    with pytest.raises(ValueError, match='ownership'):
        lifecycle.release(client, tmp_path)
    assert client.terminated == []


@pytest.mark.parametrize('redirect', ['https://wrong.example', 'https://test.example/authorize?token=private',
                                     'http://test.example'])
def test_web_registration_rejects_wrong_host_cookie_gate_and_insecure_redirect(redirect):
    client = SimpleNamespace(request=lambda *a, **k: SimpleNamespace(json=lambda: {
        'responses': [{'session': {'redirectClientTo': redirect}}]}))
    with pytest.raises(ValueError, match='public URL'):
        register_web_route(client, 'owned', 'https://test.example/v1')


def test_web_registration_registers_only_the_requested_job():
    captured = []
    def request(*args, **kwargs):
        captured.append(kwargs['json'])
        return SimpleNamespace(json=lambda: {'responses': [{'session': {'redirectClientTo': 'https://test.example'}}]})
    assert register_web_route(SimpleNamespace(request=request), 'owned', 'https://test.example/v1')['registered']
    assert captured[0]['items'] == [{'id': 'owned', 'rank': 0, 'sessionType': 'WEB'}]


def test_resume_after_activation_failure_reuses_cpu_job_and_submits_gpu_once(tmp_path, monkeypatch):
    monkeypatch.setattr(lifecycle, 'CONTROL_ROOT', tmp_path / 'control')
    monkeypatch.setenv('UCLOUD_PREPARATION_TEMPLATE_JOB_ID', 'cpu-template')
    monkeypatch.setenv('UCLOUD_PUBLIC_BASE_URL', 'https://test.example/v1')
    monkeypatch.setenv('VLLM_API_KEY', 'not-output')
    profile = validate_profile(load_json(Path(__file__).parents[1] / 'config/hosting.qwen-small.json'))
    root = tmp_path / 'bundle'; root.mkdir()
    save(root / 'hosting-profile.json', profile)
    save(root / 'runtime.json', {'remote_dir': '/work/vllm/deployments/model/bundle'})
    client = Client()
    serving = {'name': 'template', 'application': {'name': 'nginx', 'version': '1.31.2'},
               'product': profile['machine']['product'], 'parameters': {
                   'configFile': {'type': 'file', 'path': '/drive/vllm/nginx.conf'}},
               'resources': [{'type': 'file', 'path': '/drive/vllm'}, {'type': 'ingress', 'id': 'link'}]}
    prep = {**serving, 'product': {'id': 'cpu-1', 'category': 'cpu-amd-zen5', 'provider': 'ucloud'}}
    client.jobs['template'] = {'owner': {'project': 'our-project'}}
    client.jobs['cpu-template'] = {'owner': {'project': 'our-project'}}
    monkeypatch.setattr('ucloud_workflow.jobs.template_job_specification',
                        lambda c, template_job_id: prep if template_job_id == 'cpu-template' else serving)
    monkeypatch.setattr(lifecycle, 'token_status', lambda h: {'supports_allocation': True})
    def prepare(c, settings, journal, template, runtime):
        journal.submitted('preparation', c, {'name': 'owned-cpu'})
        journal.update(preparation_complete=True)
    monkeypatch.setattr(lifecycle, '_prepare_remote', prepare)
    fail = [True]
    def activate(c, s, journal, runtime):
        if fail.pop():
            raise RuntimeError('transfer failed')
    monkeypatch.setattr(lifecycle, '_activate', activate)
    with pytest.raises(RuntimeError, match='transfer'):
        lifecycle.deploy(client, None, root=root, reviewed=True)
    assert len(client.submissions) == 1
    fail.append(False)
    monkeypatch.setattr(lifecycle, 'verify_host', lambda c, j, r: j.update('endpoint_verified', endpoint_verified=True))
    result = lifecycle.deploy(client, None, root=root, reviewed=True)
    assert len(client.submissions) == 2
    assert client.submissions[1]['sshEnabled'] is False
    assert result['endpoint_verified']
    assert client.terminated == ['101']  # only the owned CPU preparation job
    lifecycle.deploy(client, None, root=root, reviewed=True)
    assert len(client.submissions) == 2
    assert client.terminated == ['101']


def test_template_project_mismatch_blocks_all_submissions(monkeypatch):
    client = Client()
    monkeypatch.setenv('UCLOUD_PREPARATION_TEMPLATE_JOB_ID', 'cpu-template')
    client.jobs['template'] = {'owner': {'project': 'another-project'}}
    client.jobs['cpu-template'] = {'owner': {'project': 'our-project'}}
    with pytest.raises(ValueError, match='UCLOUD_PROJECT'):
        lifecycle._validate_template_ownership(client)
    assert client.submissions == []


@pytest.mark.parametrize('provider_scheme', ['https', 'wss'])
def test_serving_shell_ignores_echoed_marker_and_accepts_chunked_completion(monkeypatch, provider_scheme):
    import json
    import re
    import websocket
    from ucloud_vllm_agent.transport import ServingShell
    sent = []
    class Socket:
        def send(self, value):
            sent.append(json.loads(value))
        def settimeout(self, seconds):
            assert 0 < seconds <= 15
        def recv(self):
            if not hasattr(self, 'chunks'):
                command = sent[-1]['payload']['data']
                marker = re.search(r'VLLM_DONE_[a-f0-9]+', command)[0]
                self.chunks = iter([command, '{"running": true}\r\n', marker[:20], marker[20:] + ':0\r\n'])
            return json.dumps({'payload': {'data': next(self.chunks)}})
        def close(self):
            self.closed = True
    socket = Socket()
    monkeypatch.setattr(websocket, 'create_connection', lambda *a, **k: socket)
    response = {'responses': [{'providerId': 'ucloud', 'providerDomain': provider_scheme + '://provider.example',
                               'session': {'sessionIdentifier': 'private-session'}}]}
    client = SimpleNamespace(request=lambda *a, **k: SimpleNamespace(json=lambda: response))
    result = ServingShell(client, {'id': '123', 'owner': {'createdBy': 'operator'}}).json(['python', 'remote.py', 'status'])
    assert result == {'running': True}
    assert socket.closed
    assert sent[0]['streamId'] == '0' and sent[1]['streamId'] == '1'


def test_activation_marks_uploaded_initialization_script_executable(tmp_path, monkeypatch):
    client = Client(); client.submit_job({'name': 'owned-cpu'})
    journal = Journal(tmp_path)
    journal.update(preparation_job_id='101', preparation_submission_name='owned-cpu')
    calls = []
    class Transport:
        def __init__(self, *args): pass
        def upload(self, local, remote): calls.append(('upload', remote))
        def run(self, arguments): calls.append(('run', arguments))
    monkeypatch.setattr(lifecycle, 'PreparationSSH', Transport)
    lifecycle._activate(client, client.settings, journal, {'remote_dir': '/work/vllm/deployments/model/run'})
    assert calls[0] == ('upload', '/work/vllm/init_vllm.sh')
    assert calls[1] == ('run', ['chmod', '755', '/work/vllm/init_vllm.sh'])
    assert Journal(tmp_path).data['activated']


def test_atomic_save_retries_windows_sharing_violation_without_losing_record(tmp_path, monkeypatch):
    from ucloud_vllm_agent import state
    if state.os.name != 'nt': pytest.skip('Windows sharing violation')
    target = tmp_path / 'deployment.json'; save(target, {'job_id': 'owned'})
    replace = Path.replace; attempts = []
    def intermittent(path, destination):
        attempts.append(1)
        if len(attempts) < 3: raise PermissionError('sharing violation')
        return replace(path, destination)
    monkeypatch.setattr(Path, 'replace', intermittent)
    monkeypatch.setattr(state.time, 'sleep', lambda seconds: None)
    save(target, {'job_id': 'owned', 'verified': True})
    assert load_json(target) == {'job_id': 'owned', 'verified': True}
    assert len(attempts) == 3


def test_stop_waits_for_port_release_instead_of_killing_by_port(monkeypatch):
    from ucloud_vllm_agent import remote
    attempts = []
    class Listener:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def setsockopt(self, *args): pass
        def bind(self, target):
            attempts.append(target)
            if len(attempts) < 3: raise OSError('shutdown still in progress')
    monkeypatch.setattr(remote.socket, 'socket', Listener)
    monkeypatch.setattr(remote.time, 'sleep', lambda seconds: None)
    remote.wait_for_port_release(8000)
    assert attempts == [('127.0.0.1', 8000)] * 3


@pytest.mark.parametrize('completed', [False, True])
def test_expired_preparation_is_archived_and_retried_without_stale_result(tmp_path, monkeypatch, completed):
    client = Client(); client.submit_job({'name': 'expired-cpu'})
    client.terminate_job('101')
    journal = Journal(tmp_path)
    journal.update(preparation_job_id='101', preparation_submission_name='expired-cpu',
                   preparation_submission='known', preparation_complete=completed, preparation_launched=True)
    monkeypatch.setenv('VLLM_API_KEY', 'test-only')
    monkeypatch.setattr(lifecycle, '_manifest', lambda root: [])
    calls = []
    class Transport:
        def __init__(self, settings, job, root): assert job['id'] == '102'
        def run(self, args):
            calls.append(args)
            if 'preparation-result.json' in args[-1] and 'print(' in ' '.join(args):
                return '{"state":"prepared"}'
            return ''
    monkeypatch.setattr(lifecycle, 'PreparationSSH', Transport)
    monkeypatch.setattr(lifecycle, 'wait_job', lambda c, job_id, **kw: c.retrieve_job(job_id))
    template = {'name': 'cpu-template', 'product': {'id': 'cpu', 'category': 'cpu-test', 'provider': 'test'},
                'application': {'name': 'ubuntu', 'version': '1'}, 'parameters': {}, 'resources': []}
    lifecycle._prepare_remote(client, client.settings, journal, template, {'remote_dir': '/work/vllm/new'})
    record = Journal(tmp_path).data
    assert record['preparation_job_id'] == '102' and record['preparation_complete']
    assert record['preparation_history'][0]['job_id'] == '101'
    assert client.submissions[-1]['name'].endswith('-2')
    assert any('unlink(missing_ok=True)' in ' '.join(args) for args in calls)
    assert client.terminated == ['101']  # no hosting or unrelated allocation touched


def test_activated_preparation_does_not_allocate_another_cpu(tmp_path):
    client = Client()
    journal = Journal(tmp_path)
    journal.update(preparation_complete=True, activated=True)
    lifecycle._prepare_remote(client, client.settings, journal, {}, {})
    assert client.submissions == []


def test_recovery_after_preparation_poll_failure_reuses_active_cpu(tmp_path, monkeypatch):
    client = Client()
    journal = Journal(tmp_path)
    monkeypatch.setenv('VLLM_API_KEY', 'synthetic-key')
    monkeypatch.setattr(lifecycle, '_manifest', lambda root: [])
    monkeypatch.setattr(lifecycle, 'wait_job', lambda c, job_id, **kwargs: c.retrieve_job(job_id))
    calls, fail = [], [True]
    class Transport:
        def __init__(self, *args): pass
        def run(self, args):
            calls.append(args)
            if 'print(' in ' '.join(args) and args[-1].endswith('preparation-result.json'):
                if fail[0]:
                    fail[0] = False
                    raise RuntimeError('synthetic SSH read failure')
                return '{"state":"prepared"}'
            return ''
    monkeypatch.setattr(lifecycle, 'PreparationSSH', Transport)
    template = {'application': {'name': 'coder-python', 'version': '1.89.1'},
                'product': {'id': 'cpu', 'category': 'cpu-test', 'provider': 'test'},
                'parameters': {}, 'resources': []}
    runtime = {'remote_dir': '/work/vllm/deployments/model/run'}
    with pytest.raises(RuntimeError, match='SSH read failure'):
        lifecycle._prepare_remote(client, client.settings, journal, template, runtime)
    assert journal.data['preparation_launched'] and len(client.submissions) == 1
    lifecycle._prepare_remote(client, client.settings, Journal(tmp_path), template, runtime)
    assert Journal(tmp_path).data['preparation_complete']
    assert len(client.submissions) == 1 and client.terminated == []
    assert sum('nohup' in ' '.join(args) for args in calls) == 1


def test_unknown_preparation_cannot_be_retried(tmp_path):
    client = Client()
    journal = Journal(tmp_path)
    journal.update(preparation_submission='unknown')
    with pytest.raises(ValueError, match='unknown'):
        lifecycle._prepare_remote(client, client.settings, journal,
            {'product': {'id': 'cpu', 'category': 'cpu-test', 'provider': 'test'}, 'parameters': {}, 'resources': []}, {})
    assert client.submissions == []


@pytest.fixture
def deploy_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(lifecycle, 'CONTROL_ROOT', tmp_path / 'control')
    monkeypatch.setenv('UCLOUD_PREPARATION_TEMPLATE_JOB_ID', 'cpu-template')
    monkeypatch.setenv('UCLOUD_PUBLIC_BASE_URL', 'https://test.example/v1')
    monkeypatch.setenv('VLLM_API_KEY', 'test-only')
    profile = validate_profile(load_json(Path(__file__).parents[1] / 'config/hosting.qwen-small.json'))
    client = Client()
    for job_id in ('template', 'cpu-template'):
        client.jobs[job_id] = {'owner': {'project': 'our-project'}}
    serving = {'application': {'name': 'nginx', 'version': '1.31.2'},
               'product': profile['machine']['product'], 'parameters': {
                   'configFile': {'type': 'file', 'path': '/drive/vllm/nginx.conf'}},
               'resources': [{'type': 'file', 'path': '/drive/vllm'}, {'type': 'ingress', 'id': 'link'}]}
    prep = {**serving, 'product': {'id': 'cpu', 'category': 'cpu-test', 'provider': 'test'}}
    monkeypatch.setattr('ucloud_workflow.jobs.template_job_specification',
                        lambda c, template_job_id: prep if template_job_id == 'cpu-template' else serving)
    monkeypatch.setattr(lifecycle, 'token_status', lambda h: {'supports_allocation': True})
    def bundle(name, p=profile):
        root = tmp_path / name; root.mkdir()
        save(root / 'hosting-profile.json', p)
        save(root / 'runtime.json', {'remote_dir': '/work/vllm/' + name})
        return root
    monkeypatch.setattr(lifecycle, 'inspect_model', lambda model, revision: {'model': model, 'revision': revision})
    created = []
    def prepare_profile(p, metadata, output):
        created.append(deepcopy(p)); return bundle('restored-' + str(len(created)), p)
    monkeypatch.setattr(lifecycle, 'prepare_profile', prepare_profile)
    def prepare(c, s, j, t, r):
        j.submitted('preparation', c, {'name': 'cpu-' + j.root.name})
        j.update(preparation_complete=True)
    monkeypatch.setattr(lifecycle, '_prepare_remote', prepare)
    monkeypatch.setattr(lifecycle, '_activate', lambda c, s, j, r: j.update(activated=True))
    monkeypatch.setattr(lifecycle, 'verify_host', lambda c, j, r: j.update('endpoint_verified', endpoint_verified=True))
    return client, profile, bundle, created


def test_replacement_failure_keeps_predecessor_and_rollback_resumes_once(tmp_path, monkeypatch, deploy_fixture):
    client, profile, bundle, created = deploy_fixture
    old = bundle('old'); old_j = Journal(old)
    old_id = old_j.submitted('hosting', client, {'name': 'old-owned'})
    old_j.update('endpoint_verified', reviewed=True, endpoint_verified=True)
    new = bundle('new')
    save(lifecycle.CONTROL_ROOT / 'current.json', {'deployment': str(old)})
    verify = lifecycle.verify_host
    monkeypatch.setattr(lifecycle, 'verify_host', lambda *args: (_ for _ in ()).throw(ValueError('verification failed')))
    with pytest.raises(ValueError, match='verification failed'):
        lifecycle.deploy(client, None, root=new, replace=old, reviewed=True)
    assert Journal(old).data['state'] == 'replacement_pending'
    assert not Journal(old).data['endpoint_verified']
    assert Journal(new).data['replacement'] == str(old)
    monkeypatch.setattr(lifecycle, 'verify_host', verify)
    result = lifecycle.rollback(client, new)
    assert result['endpoint_verified'] and result['restored_from'] == str(old)
    assert created == [profile]  # exact previous model, revision, machine and limits
    assert Journal(new).data['state'] == 'rolled_back'
    count = len(client.submissions)
    lifecycle.rollback(client, new)
    assert len(client.submissions) == count
    assert len(created) == 1
    assert old_id in client.terminated


def test_rollback_unknown_replacement_blocks_all_new_jobs(tmp_path, deploy_fixture):
    client, profile, bundle, created = deploy_fixture
    old = bundle('old'); Journal(old).update(reviewed=True)
    new = bundle('new')
    Journal(new).update(replacement=str(old), hosting_submission='unknown')
    with pytest.raises(ValueError, match='unknown'):
        lifecycle.rollback(client, new)
    assert client.submissions == [] and created == []


def test_released_deployment_cannot_be_recovered(tmp_path, deploy_fixture):
    client, profile, bundle, created = deploy_fixture
    root = bundle('released'); Journal(root).update('released', reviewed=True)
    with pytest.raises(ValueError, match='retired'):
        lifecycle.deploy(client, None, root=root, reviewed=True)
    assert client.submissions == []


def test_renewal_preserves_pinned_profile_and_resumes_without_duplicates(tmp_path, deploy_fixture):
    client, profile, bundle, created = deploy_fixture
    old = bundle('old')
    journal = Journal(old)
    journal.submitted('hosting', client, {'name': 'owned-old'})
    journal.update(reviewed=True)
    result = lifecycle.renew(client, old, 3)
    expected = deepcopy(profile); expected['hours'] = 3
    assert created == [expected]
    assert result['renewal_of'] == str(old) and result['endpoint_verified']
    assert Journal(old).data['state'] == 'renewed'
    count = len(client.submissions)
    lifecycle.renew(client, old, 3)
    assert len(client.submissions) == count
    with pytest.raises(ValueError, match='different hours'):
        lifecycle.renew(client, old, 4)
    assert len(client.submissions) == count


def test_rollback_acknowledgement_loss_blocks_retry_then_reconciles(tmp_path, monkeypatch, deploy_fixture):
    client, profile, bundle, created = deploy_fixture
    old = bundle('old'); Journal(old).update(reviewed=True)
    failed = bundle('failed'); Journal(failed).update(replacement=str(old))
    # Simulate acknowledgement loss at the GPU submit, after known CPU cleanup.
    submit = client.submit_job
    def submit_with_loss(spec):
        client.lost_response = spec['application']['name'] == 'nginx' if 'application' in spec else False
        return submit(spec)
    monkeypatch.setattr(client, 'submit_job', submit_with_loss)
    with pytest.raises(RuntimeError, match='unknown'):
        lifecycle.rollback(client, failed)
    restored = tmp_path / 'restored-1'
    assert Journal(restored).data['hosting_submission'] == 'unknown'
    count = len(client.submissions)
    with pytest.raises(ValueError, match='unknown'):
        lifecycle.rollback(client, failed)
    assert len(client.submissions) == count and len(created) == 1
    lifecycle.reconcile(client, restored, str(100 + count), 'hosting')
    result = lifecycle.deploy(client, None, root=restored, reviewed=True)
    assert result['endpoint_verified'] and Journal(failed).data['state'] == 'rolled_back'
    assert len(client.submissions) == count


def test_rollback_before_cutover_preserves_running_predecessor(tmp_path, deploy_fixture):
    client, profile, bundle, created = deploy_fixture
    old = bundle('old'); journal = Journal(old)
    journal.submitted('hosting', client, {'name': 'owned-old'})
    journal.update(reviewed=True)
    failed = bundle('failed'); Journal(failed).update(replacement=str(old))
    with pytest.raises(ValueError, match='previous allocation is still active'):
        lifecycle.rollback(client, failed)
    assert len(client.submissions) == 1 and client.terminated == [] and created == []


@pytest.mark.parametrize('operation', ['stop', 'restart'])
def test_shutdown_transport_budget_covers_both_port_waits(tmp_path, monkeypatch, operation):
    monkeypatch.setattr(lifecycle, 'CONTROL_ROOT', tmp_path / 'control')
    client = Client(); journal = Journal(tmp_path)
    journal.submitted('hosting', client, {'name': 'owned'})
    save(tmp_path/'runtime.json', {'venv_dir':'/work/vllm/.venv','remote_dir':'/work/vllm/test'})
    calls=[]
    class Shell:
        def __init__(self, *args): pass
        def json(self, *args): return {'running':True}
        def run(self, args, timeout=60): calls.append((args[-1],timeout))
    monkeypatch.setattr(lifecycle, 'ServingShell', Shell)
    monkeypatch.setattr(lifecycle, 'verify_host', lambda c,j,r: j.update(endpoint_verified=True))
    getattr(lifecycle, operation)(client,tmp_path)
    assert ('stop',180) in calls
    assert client.terminated == []
