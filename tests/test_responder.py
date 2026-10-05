import importlib.util
from pathlib import Path
from fastapi.testclient import TestClient

spec = importlib.util.spec_from_file_location('responder', Path(__file__).parents[1] / 'incident-response/server.py')
responder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(responder)


def test_resolved_ignored_firing_saved_and_duplicate_suppressed(tmp_path, monkeypatch):
    queued = []
    class Pool:
        def submit(self, *args):
            queued.append(args)
    monkeypatch.setattr(responder, 'POOL', Pool())
    monkeypatch.setattr(responder, 'INCIDENTS', tmp_path)
    monkeypatch.setattr(responder, 'ACTIVE', set())
    with TestClient(responder.app) as client:
        assert client.post('/alerts', json={'alerts': [{'status': 'resolved'}]}).json() == {'jobs': []}
        body = {'alerts': [{'status': 'firing', 'labels': {'test': 'true'}}]}
        result = client.post('/alerts', json=body)
        assert result.status_code == 202
        folder = tmp_path / result.json()['jobs'][0]['id']
        assert (folder / 'alert.json').exists()
        assert client.post('/alerts', json=body).json()['jobs'][0]['state'] == 'duplicate'
        assert len(queued) == 1
        assert client.post('/alerts', json={'alerts': []}).status_code == 422


def test_test_alert_launches_read_only_agent_and_saves_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(responder, 'ROOT', tmp_path)
    monkeypatch.setattr(responder, 'fetch', lambda *args, **kwargs: {})
    folder = tmp_path / 'incident-response/incidents/test-job'
    folder.mkdir(parents=True)
    seen = []
    def run(command, **kwargs):
        seen.append((command, kwargs))
        output = Path(command[command.index('--output-last-message') + 1])
        output.write_text('Test acknowledged. No incident to fix.')
        class Result:
            returncode = 0
        return Result()
    monkeypatch.setattr(responder.subprocess, 'run', run)
    responder.investigate(folder, {'labels': {'test': 'true'}, 'annotations': {}}, 'test')
    import json
    assert json.loads((folder / 'status.json').read_text())['state'] == 'completed'
    assert (folder / 'evidence.json').exists()
    command, options = seen[0]
    assert command[command.index('--sandbox') + 1] == 'read-only'
    assert command[-1] == '-'
    assert 'untrusted data' in options['input']
    assert options['timeout'] == 600
    assert not options.get('shell', False)


def test_agent_failure_is_not_reported_as_success(tmp_path, monkeypatch):
    monkeypatch.setattr(responder, 'ROOT', tmp_path)
    monkeypatch.setattr(responder, 'fetch', lambda *args, **kwargs: {'collection_error': 'unavailable'})
    folder = tmp_path / 'incident-response/incidents/failed-job'
    folder.mkdir(parents=True)
    def fail(*args, **kwargs):
        raise FileNotFoundError('Codex executable missing')
    monkeypatch.setattr(responder.subprocess, 'run', fail)
    responder.investigate(folder, {'labels': {}, 'annotations': {}}, 'test')
    import json
    status = json.loads((folder / 'status.json').read_text())
    assert status['state'] == 'failed'
    assert 'Codex executable missing' in status['error']
    assert 'collection_error' in (folder / 'evidence.json').read_text()
