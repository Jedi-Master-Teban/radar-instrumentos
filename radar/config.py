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
    load_dotenv(home / ".env", override=True)  # lo guardado desde el tablero manda
    return Ajustes(
        nim_api_key=os.environ.get("NIM_API_KEY", ""),
        nim_model=os.environ.get("NIM_MODEL", ""),
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
        home=home,
    )


CLAVES_SECRETAS = ("NIM_API_KEY", "NIM_MODEL", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")


def guardar_secretos(home: Path, valores: dict[str, str]) -> None:
    """Guarda claves en ~/.radar/.env (permisos 600). Los campos vacíos conservan el valor anterior."""
    ruta = home / ".env"
    actuales: dict[str, str] = {}
    if ruta.exists():
        for linea in ruta.read_text().splitlines():
            if "=" in linea and not linea.startswith("#"):
                k, v = linea.split("=", 1)
                actuales[k.strip()] = v.strip()
    for k, v in valores.items():
        if k in CLAVES_SECRETAS and v and v.strip():
            actuales[k] = v.strip().replace("\n", "")
    ruta.write_text("".join(f"{k}={v}\n" for k, v in actuales.items()))
    ruta.chmod(0o600)
    for k, v in actuales.items():
        os.environ[k] = v
