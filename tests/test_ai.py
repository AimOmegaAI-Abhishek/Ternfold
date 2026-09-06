from ternfold import ai


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": '{"freight": null}'}}]}


def test_nvidia_provider_status_and_request(monkeypatch):
    monkeypatch.setenv("TERNFOLD_AI_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return FakeResponse()

    monkeypatch.setattr(ai.httpx, "post", fake_post)
    status = ai.extraction_status()
    result = ai.propose_from_text("Freight is not stated.")

    assert status["provider"] == "nvidia"
    assert status["available"] is True
    assert status["model"] == "deepseek-ai/deepseek-v4-pro-0813"
    assert result == '{"freight": null}'
    assert captured["url"] == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert captured["headers"] == {"Authorization": "Bearer test-key"}
    assert captured["json"]["stream"] is False
    assert captured["json"]["chat_template_kwargs"] == {"thinking": False}
    assert "Never calculate contribution" in captured["json"]["messages"][0]["content"]


def test_nvidia_without_key_keeps_manual_fallback(monkeypatch):
    monkeypatch.setenv("TERNFOLD_AI_PROVIDER", "nvidia")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    status = ai.extraction_status()

    assert status["available"] is False
    assert "Manual review remains fully available" in status["message"]
