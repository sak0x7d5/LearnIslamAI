import asyncio
import re
import sys
from pathlib import Path

import pytest
from pydantic import SecretStr


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.api_keys import EnvFileService  # noqa: E402
from core.llm import (  # noqa: E402
    GOOGLE,
    OPENROUTER,
    PROVIDERS,
    ProviderError,
    classify_failure,
    make_key_validator,
    resolve_model,
    resolve_provider,
)


class _Status(Exception):
    """Stand-in for a provider SDK error, which carries a status_code."""

    def __init__(self, message: str, status_code: object):
        super().__init__(message)
        self.status_code = status_code


def _reader(*present: str):
    return lambda name: SecretStr("value") if name in present else None


def test_registry_entries_are_well_formed():
    for provider in PROVIDERS:
        assert provider.id == provider.id.lower()
        assert re.fullmatch(EnvFileService._KEY_RE.pattern, provider.key_env)
        assert provider.console_url.startswith("https://")
        assert provider.default_model.strip()
        assert provider.rejecting_statuses


def test_provider_follows_whichever_key_is_configured():
    assert resolve_provider(_reader("GOOGLE_API_KEY"), "") is GOOGLE
    assert resolve_provider(_reader("OPENROUTER_API_KEY"), "") is OPENROUTER


def test_both_keys_present_keeps_the_existing_gemini_install_working():
    reader = _reader("GOOGLE_API_KEY", "OPENROUTER_API_KEY")

    assert resolve_provider(reader, "") is GOOGLE


def test_no_key_at_all_falls_back_to_the_free_router():
    assert resolve_provider(_reader(), "") is OPENROUTER


def test_explicit_choice_overrides_the_configured_key():
    reader = _reader("GOOGLE_API_KEY")

    assert resolve_provider(reader, "openrouter") is OPENROUTER
    assert resolve_provider(reader, "  OpenRouter  ") is OPENROUTER


def test_unknown_provider_id_falls_back_to_detection():
    assert resolve_provider(_reader("GOOGLE_API_KEY"), "gpt5") is GOOGLE


def test_model_comes_from_the_environment_then_the_default(monkeypatch):
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    assert resolve_model(OPENROUTER) == OPENROUTER.default_model

    monkeypatch.setenv("OPENROUTER_MODEL", "vendor/model:free")
    assert resolve_model(OPENROUTER) == "vendor/model:free"


def test_plaintext_base_url_is_refused_before_a_key_is_sent(monkeypatch):
    monkeypatch.setattr("core.llm.OPENROUTER_BASE_URL", "http://openrouter.ai/api/v1")

    with pytest.raises(ProviderError):
        resolve_provider(_reader("OPENROUTER_API_KEY"), "openrouter")


def test_400_means_a_bad_key_for_gemini_but_a_bad_model_for_openrouter():
    """Gemini answers 400 for a malformed key; OpenRouter answers 400 for the model."""

    google = classify_failure(GOOGLE, "gemini-3.1-flash-lite", _Status("bad", 400))
    openrouter = classify_failure(OPENROUTER, "vendor/model", _Status("bad", 400))

    assert google.status == "invalid"
    assert openrouter.status == "unavailable"
    assert "model name" in openrouter.message


def test_401_rejects_the_key_for_every_provider():
    for provider in PROVIDERS:
        result = classify_failure(provider, "any-model", _Status("nope", 401))
        assert result.status == "invalid"
        assert provider.label in result.message


def test_missing_credit_does_not_ask_for_another_key():
    result = classify_failure(OPENROUTER, "vendor/model", _Status("payment", 402))

    # "invalid" would loop the key prompt, which cannot fix a credit balance.
    assert result.status == "unavailable"
    assert "credit" in result.message


def test_network_and_timeout_failures_are_unavailable():
    assert classify_failure(GOOGLE, "m", OSError("no route")).status == "unavailable"
    assert classify_failure(GOOGLE, "m", asyncio.TimeoutError()).status == "unavailable"


def test_classifier_never_echoes_provider_text_or_the_key():
    leak = "sk-or-v1-DEADBEEF and the user's question text"

    result = classify_failure(OPENROUTER, "vendor/model", _Status(leak, 500))

    assert "sk-or-v1-DEADBEEF" not in result.message
    assert "question text" not in result.message


def test_a_model_without_tool_calling_is_rejected_by_name():
    async def no_tool_call(_provider, _model, _key):
        return False

    validate = make_key_validator(OPENROUTER, "vendor/toolless", probe=no_tool_call)
    result = asyncio.run(validate(SecretStr("secret-value")))

    assert not result.is_valid
    assert "vendor/toolless" in result.message
    assert "OPENROUTER_MODEL" in result.message
    assert "secret-value" not in result.message


def test_a_tool_capable_model_validates():
    async def calls_a_tool(_provider, _model, _key):
        return True

    validate = make_key_validator(GOOGLE, "gemini-3.1-flash-lite", probe=calls_a_tool)
    result = asyncio.run(validate(SecretStr("secret-value")))

    assert result.is_valid
    assert "secret-value" not in result.message


def test_probe_failures_are_classified_not_raised():
    async def rejected(_provider, _model, _key):
        raise _Status("denied", 403)

    validate = make_key_validator(OPENROUTER, "vendor/model", probe=rejected)

    assert asyncio.run(validate(SecretStr("k"))).status == "invalid"


def test_build_graph_uses_the_selected_provider(tmp_path):
    pytest.importorskip("langgraph.graph")
    pytest.importorskip("langchain_community")
    from types import SimpleNamespace

    from core.graph import build_graph
    from core.llm import Provider

    seen: dict[str, object] = {}

    def factory(model, api_key, max_retries):
        seen["model"] = model
        seen["api_key"] = api_key
        return SimpleNamespace(bind_tools=lambda tools: SimpleNamespace(ainvoke=None))

    fake = Provider(
        id="fake",
        label="Fake",
        key_env="FAKE_API_KEY",
        model_env="FAKE_MODEL",
        default_model="fake/model",
        console_url="https://example.invalid/keys",
        key_placeholder="key",
        factory=factory,
        rejecting_statuses=frozenset({"401"}),
    )

    quran_dir = tmp_path / "quran" / "english"
    quran_dir.mkdir(parents=True)
    key = SecretStr("secret-value")
    build_graph(
        api_key=key,
        coordinator=SimpleNamespace(quran_dir=quran_dir),
        provider=fake,
        model_name="fake/model",
    )

    assert seen["model"] == "fake/model"
    assert seen["api_key"] is key
