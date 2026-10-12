from ozon_common.settings import ai_config


def test_deepseek_platform_is_openai_compatible_and_uses_short_model_name():
    settings = {
        "ai_platforms": [{"name": "DeepSeek", "base": "https://api.deepseek.com/v1", "key": "DS"}],
        "ai_text": {"platform": "DeepSeek", "model": "deepseek-ai/deepseek-v4-flash"},
    }

    assert ai_config(settings, "text") == {
        "engine": "openai",
        "base": "https://api.deepseek.com/v1",
        "key": "DS",
        "model": "deepseek-v4-flash",
    }
