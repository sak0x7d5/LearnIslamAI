from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import SecretStr


ValidationStatus = Literal["valid", "invalid", "unavailable"]


@dataclass(frozen=True)
class ValidationResult:
    status: ValidationStatus
    message: str

    @property
    def is_valid(self) -> bool:
        return self.status == "valid"


class EnvFileService:
    """Read and atomically update the repository-local, ignored .env file."""

    _KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

    def __init__(self, env_path: Path):
        self.env_path = Path(env_path)

    def read_secret(self, name: str) -> SecretStr | None:
        value = os.environ.get(name)
        if not value and self.env_path.exists():
            raw = dotenv_values(self.env_path).get(name)
            value = raw if isinstance(raw, str) else None
        if not value or not value.strip():
            return None
        return SecretStr(value.strip())

    def upsert_secret(self, name: str, secret: SecretStr) -> None:
        if not self._KEY_RE.fullmatch(name):
            raise ValueError("Invalid environment variable name")

        value = secret.get_secret_value().strip()
        if not value or "\n" in value or "\r" in value:
            raise ValueError("Secret must be a non-empty single line")

        self.env_path.parent.mkdir(parents=True, exist_ok=True)
        existing = (
            self.env_path.read_text(encoding="utf-8").splitlines() if self.env_path.exists() else []
        )
        replacement = f"{name}={value}"
        output: list[str] = []
        replaced = False
        for line in existing:
            if line.lstrip().startswith(f"{name}="):
                if not replaced:
                    output.append(replacement)
                    replaced = True
                continue
            output.append(line)

        if not replaced:
            if output and output[-1] != "":
                output.append("")
            output.append(replacement)

        content = "\n".join(output).rstrip("\n") + "\n"
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{self.env_path.name}.",
            suffix=".tmp",
            dir=self.env_path.parent,
            delete=False,
        )
        temp_path = Path(handle.name)
        try:
            with handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.env_path)
        finally:
            temp_path.unlink(missing_ok=True)


class ApiKeyService:
    """Own one provider's key lifecycle without exposing its value to logs or UI props."""

    def __init__(
        self,
        env_file: EnvFileService,
        validator: Callable[[SecretStr], Awaitable[ValidationResult]],
        key_env: str = "GOOGLE_API_KEY",
    ):
        self.env_file = env_file
        self.validator = validator
        self.key_env = key_env

    def read(self) -> SecretStr | None:
        return self.env_file.read_secret(self.key_env)

    async def validate(self, key: SecretStr) -> ValidationResult:
        return await self.validator(key)

    async def validate_and_save(self, key: SecretStr) -> ValidationResult:
        result = await self.validate(key)
        if result.is_valid:
            self.save(key)
        return result

    def save(self, key: SecretStr) -> None:
        self.env_file.upsert_secret(self.key_env, key)
