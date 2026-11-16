"""Ajustes del entorno (.env). Los parámetros de negocio viven en la base de datos."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"


@dataclass
class Ajustes:
    nim_api_key: str
    nim_model: str
    telegram_bot_token: str
    telegram_chat_id: str
    home: Path

    @property
    def ruta_db(self) -> str:
        return str(self.home / "radar.db")

    @property
    def perfil_fb(self) -> str:
        return str(self.home / "fb-profile")


def cargar(env_file: str | None = ".env") -> Ajustes:
    if env_file:
        load_dotenv(env_file)
    home = Path(os.environ.get("RADAR_HOME", "~/.radar")).expanduser()
    home.mkdir(parents=True, exist_ok=True)
    return Ajustes(
        nim_api_key=os.environ.get("NIM_API_KEY", ""),
        nim_model=os.environ.get("NIM_MODEL", ""),
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
        home=home,
    )
