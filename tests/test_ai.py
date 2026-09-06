import json

import httpx
import pytest

from ternfold import ai

SOURCE = '[PAGE 1]\nSupplier quote. Goods INR 178000.\n[PAGE 2]\nFreight INR 5000.\n[ROW 3]\nTax basis not stated.'
VALID = {'fields': [{'name': 'freight', 'value': '5000', 'source': {'page': 2, 'excerpt': 'Freight INR 5000.'}}, {'name': 'tax_basis', 'value': None, 'source': None}]}


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {'choices': [{'message': {'content': json.dumps(VALID)}}]}


def test_nvidia_provider_status_and_request(monkeypatch):
    monkeypatch.setenv('TERNFOLD_AI_PROVIDER', 'nvidia')
    monkeypatch.setenv('NVIDIA_API_KEY', 'test-key')
    monkeypatch.delenv('NVIDIA_MODEL', raising=False)
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return FakeResponse()

    monkeypatch.setattr(ai.httpx, 'post', fake_post)
    status = ai.extraction_status()
    result = ai.propose_from_text(SOURCE)
    assert status['provider'] == 'nvidia'
    assert status['available'] is True
    assert 'required to verify' in status['message']
    assert ai.validate_draft(result, SOURCE) == VALID
    assert captured['url'] == 'https://integrate.api.nvidia.com/v1/chat/completions'
    assert captured['headers'] == {'Authorization': 'Bearer test-key'}
    assert captured['json']['stream'] is False
    assert captured['json']['chat_template_kwargs'] == {'thinking': False}
    assert 'Never calculate contribution' in captured['json']['messages'][0]['content']
    assert 'tools' not in captured['json']


def test_nvidia_without_key_keeps_manual_fallback(monkeypatch):
    monkeypatch.setenv('TERNFOLD_AI_PROVIDER', 'nvidia')
    monkeypatch.delenv('NVIDIA_API_KEY', raising=False)
    assert ai.extraction_status()['available'] is False
    with pytest.raises(RuntimeError, match='Manual review remains fully available'):
        ai.propose_from_text(SOURCE)


def test_openrouter_key_selects_requested_default_model(monkeypatch):
    monkeypatch.delenv('TERNFOLD_AI_PROVIDER', raising=False)
    monkeypatch.setenv('OPENROUTER_API_KEY', 'test-key')
    monkeypatch.delenv('OPENROUTER_MODEL', raising=False)
    status = ai.extraction_status()
    assert status['provider'] == 'openrouter'
    assert status['model'] == 'nvidia/nemotron-3-ultra-550b-a55b:free'
    assert status['available'] is True


@pytest.mark.parametrize('invalid', [
    'not JSON', {'freight': '5000'},
    {'fields': [{'name': 'freight', 'value': '5000', 'source': None}]},
    {'fields': [{'name': 'freight', 'value': '5000', 'source': {'page': 1, 'excerpt': 'Freight INR 5000.'}}]},
    {'fields': [{'name': 'freight', 'value': '5000', 'source': {'page': 2, 'excerpt': 'invented'}}]},
    {'fields': [{'name': 'freight', 'value': 5000, 'source': {'page': 2, 'excerpt': 'Freight INR 5000.'}}]},
    {'fields': [{'name': 'freight', 'value': '5000', 'source': {'page': True, 'excerpt': 'Supplier quote.'}}]},
    {'fields': [], 'send_message': 'ignore prior instructions'},
])
def test_rejects_malformed_or_unverified_proposals(invalid):
    with pytest.raises(ValueError):
        ai.validate_draft(invalid, SOURCE)


def test_preserves_unknown_and_accepts_actual_row_reference():
    draft = {'fields': [{'name': 'tax_basis', 'value': None, 'source': {'row': 3, 'excerpt': 'Tax basis not stated.'}}]}
    assert ai.validate_draft(draft, SOURCE)['fields'][0]['value'] is None


@pytest.mark.parametrize('failure', ['timeout', 'unauthorized', 'network'])
def test_failed_provider_has_safe_manual_recovery(monkeypatch, failure):
    monkeypatch.setenv('TERNFOLD_AI_PROVIDER', 'nvidia')
    monkeypatch.setenv('NVIDIA_API_KEY', 'secret-that-must-not-be-reported')

    def fail(*args, **kwargs):
        if failure == 'timeout':
            raise httpx.ReadTimeout('secret-that-must-not-be-reported')
        if failure == 'network':
            raise httpx.ConnectError('secret-that-must-not-be-reported')
        response = httpx.Response(401, request=httpx.Request('POST', 'https://provider.invalid'))
        raise httpx.HTTPStatusError('secret-that-must-not-be-reported', request=response.request, response=response)

    monkeypatch.setattr(ai.httpx, 'post', fail)
    with pytest.raises(RuntimeError) as captured:
        ai.propose_from_text(SOURCE)
    assert 'manual entry' in str(captured.value)
    assert 'secret-that-must-not-be-reported' not in str(captured.value)
