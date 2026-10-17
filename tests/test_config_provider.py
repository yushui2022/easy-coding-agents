import importlib


def test_deepseek_provider_config(monkeypatch):
    # Provider defaults must not depend on a developer's private .env.
    monkeypatch.setattr("dotenv.load_dotenv", lambda **kwargs: None)
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.delenv("MODEL_NAME", raising=False)

    import core.config as config

    importlib.reload(config)
    assert config.Config.provider_label() == "DeepSeek"
    assert config.Config.base_url() == "https://api.deepseek.com"
    assert config.Config.api_key() == "test-key"
    assert config.Config.MODEL_NAME == "deepseek-v4-flash"
