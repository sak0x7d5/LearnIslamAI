import asyncio
import sys
from pathlib import Path

from pydantic import SecretStr


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.api_keys import ApiKeyService, EnvFileService, ValidationResult  # noqa: E402


def test_env_file_upsert_preserves_other_values(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("CHAINLIT_AUTH_SECRET=keep-me\nOTHER=value\n", encoding="utf-8")
    service = EnvFileService(env_path)

    service.upsert_secret("GOOGLE_API_KEY", SecretStr("new-key"))

    stored = env_path.read_text(encoding="utf-8")
    assert "CHAINLIT_AUTH_SECRET=keep-me" in stored
    assert "OTHER=value" in stored
    assert stored.count("GOOGLE_API_KEY=new-key") == 1
    assert service.read_secret("GOOGLE_API_KEY").get_secret_value() == "new-key"


def test_env_file_rejects_multiline_secret(tmp_path):
    service = EnvFileService(tmp_path / ".env")
    try:
        service.upsert_secret("GOOGLE_API_KEY", SecretStr("bad\nINJECTED=yes"))
    except ValueError as exc:
        assert "single line" in str(exc)
    else:
        raise AssertionError("multiline secret was accepted")


def test_environment_value_takes_precedence(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("GOOGLE_API_KEY=file-key\n", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_API_KEY", "process-key")

    value = EnvFileService(env_path).read_secret("GOOGLE_API_KEY")

    assert value.get_secret_value() == "process-key"


def test_api_key_validation_and_save_do_not_expose_secret(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    seen: list[str] = []

    async def validator(secret: SecretStr) -> ValidationResult:
        seen.append(secret.get_secret_value())
        return ValidationResult("valid", "Key accepted")

    service = ApiKeyService(EnvFileService(tmp_path / ".env"), validator)
    key = SecretStr("private-value")
    result = asyncio.run(service.validate_and_save(key))

    assert result.is_valid
    assert "private-value" not in result.message
    assert seen == ["private-value"]
    assert repr(key) == "SecretStr('**********')"


def test_rejected_and_unavailable_keys_are_never_saved(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    env_path = tmp_path / ".env"

    async def rejected(_secret: SecretStr) -> ValidationResult:
        return ValidationResult("invalid", "Google rejected this API key.")

    rejected_service = ApiKeyService(EnvFileService(env_path), rejected)
    rejected_result = asyncio.run(
        rejected_service.validate_and_save(SecretStr("rejected-secret-value"))
    )

    assert rejected_result.status == "invalid"
    assert not env_path.exists()

    async def unavailable(_secret: SecretStr) -> ValidationResult:
        return ValidationResult("unavailable", "Google was unavailable.")

    unavailable_service = ApiKeyService(EnvFileService(env_path), unavailable)
    unavailable_result = asyncio.run(
        unavailable_service.validate_and_save(SecretStr("unavailable-secret-value"))
    )

    assert unavailable_result.status == "unavailable"
    assert not env_path.exists()


def test_switching_providers_keeps_the_other_key(tmp_path, monkeypatch):
    """Both provider keys must be able to coexist in one .env file."""

    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("GOOGLE_API_KEY=google-key\n", encoding="utf-8")

    async def accept(_secret: SecretStr) -> ValidationResult:
        return ValidationResult("valid", "ok")

    service = ApiKeyService(EnvFileService(env_path), accept, "OPENROUTER_API_KEY")
    asyncio.run(service.validate_and_save(SecretStr("router-key")))

    stored = env_path.read_text(encoding="utf-8")
    assert "GOOGLE_API_KEY=google-key" in stored
    assert "OPENROUTER_API_KEY=router-key" in stored
    assert service.read().get_secret_value() == "router-key"
