"""SecretsConfig — reads env vars + .env for secret-bearing config.

Values are wrapped in ``SecretStr`` so they never leak into logs or CLI
output. The only public surface is boolean ``is_*_present()`` methods —
callers get "the secret is configured" without ever being handed the value
(except via explicit ``.get_secret_value()``, which callers that need the
raw key call deliberately).
"""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class SecretsConfig(BaseSettings):
    """Presence-tracker for the 4 known secrets Phase 1-5 need.

    Fields use ``alias=`` so pydantic-settings picks them up from the env
    with their canonical upper-case names (``ANTHROPIC_API_KEY`` etc.).
    ``populate_by_name=True`` lets tests also set them by the lower-case
    field name if convenient.
    """

    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openclaw_gateway_token: SecretStr | None = Field(default=None, alias="OPENCLAW_GATEWAY_TOKEN")
    telegram_bot_token: SecretStr | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str | None = Field(default=None, alias="TELEGRAM_CHAT_ID")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    def is_anthropic_present(self) -> bool:
        return self.anthropic_api_key is not None and bool(
            self.anthropic_api_key.get_secret_value()
        )

    def is_openclaw_present(self) -> bool:
        return self.openclaw_gateway_token is not None and bool(
            self.openclaw_gateway_token.get_secret_value()
        )

    def is_telegram_present(self) -> bool:
        return (
            self.telegram_bot_token is not None
            and bool(self.telegram_bot_token.get_secret_value())
            and self.telegram_chat_id is not None
            and bool(self.telegram_chat_id)
        )
