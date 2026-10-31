"""Pantalla de Configuración del panel: qué claves hay, dónde se consiguen
y cómo se guardan en .env sin tener que editar el archivo a mano.

Seguridad: las claves son secretas. Por eso
  - el panel nunca las devuelve completas (solo "eyJh…x9Q"),
  - y solo se pueden cambiar desde el propio ordenador (127.0.0.1),
    aunque el panel se abra en la red local.
"""

from __future__ import annotations

import re

from .config import Config, guardar_en_env

CAMPOS = [
    {"clave": "AEMET_API_KEY", "fuente": "aemet", "etiqueta": "Clave de AEMET (meteorología)",
     "secreto": True, "obligatorio": True,
     "enlace": "https://opendata.aemet.es/centrodedescargas/altaUsuario",
     "ayuda": "Gratis. Pon tu email en la web de AEMET y te llega un correo con un enlace; "
              "al confirmarlo te envían otro correo con la clave (un texto muy largo que empieza por eyJ)."},
    {"clave": "WAQI_TOKEN", "fuente": "waqi", "etiqueta": "Token de WAQI (calidad del aire)",
     "secreto": True, "obligatorio": True,
     "enlace": "https://aqicn.org/data-platform/token/",
     "ayuda": "Gratis. Pon tu email y nombre, confirma el correo y te mostrarán el token (unas 40 letras y números)."},
    {"clave": "ESIOS_TOKEN", "fuente": "pvpc", "etiqueta": "Token de ESIOS (opcional)",
     "secreto": True, "obligatorio": False,
     "enlace": "mailto:consultasios@ree.es",
     "ayuda": "No hace falta: sin él, el precio de la luz se saca de la API pública de REE. "
              "Si quieres el oficial, pídelo por email a consultasios@ree.es."},
    {"clave": "SAIH_CODIGOS", "fuente": "saih", "etiqueta": "Códigos de estaciones SAIH Ebro",
     "secreto": False, "obligatorio": False,
     "enlace": "https://www.saihebro.com",
     "ayuda": "Formato estacion=CODIGO separados por comas. Estaciones: ullibarri, urrunaga, "
              "zadorra_vitoria, zadorra_arce. Ejemplo: urrunaga=E028,ullibarri=E0xx"},
    {"clave": "TELEGRAM_BOT_TOKEN", "fuente": None, "etiqueta": "Token del bot de Telegram",
     "secreto": True, "obligatorio": False,
     "enlace": "https://t.me/BotFather",
     "ayuda": "En Telegram, habla con @BotFather, escribe /newbot y sigue los pasos. Te da un token como 123456:ABC…"},
    {"clave": "TELEGRAM_CHAT_ID", "fuente": None, "etiqueta": "Tu chat_id de Telegram",
     "secreto": False, "obligatorio": False, "enlace": None,
     "ayuda": "Escribe algo a tu bot y abre https://api.telegram.org/bot<TOKEN>/getUpdates: "
              "busca \"chat\":{\"id\":123456789 y copia ese número."},
]
PERMITIDAS = {c["clave"] for c in CAMPOS}


def _valor(config: Config, clave: str) -> str | None:
    mapa = {
        "AEMET_API_KEY": config.aemet_api_key, "WAQI_TOKEN": config.waqi_token,
        "ESIOS_TOKEN": config.esios_token,
        "SAIH_CODIGOS": ",".join(f"{k}={v}" for k, v in config.saih_codigos.items()) or None,
        "TELEGRAM_BOT_TOKEN": config.telegram_bot_token, "TELEGRAM_CHAT_ID": config.telegram_chat_id,
    }
    return mapa.get(clave)


def enmascarar(valor: str) -> str:
    return valor if len(valor) <= 8 else f"{valor[:4]}…{valor[-3:]}"


def estado(config: Config, editable: bool) -> dict:
    campos = []
    for c in CAMPOS:
        v = _valor(config, c["clave"])
        campos.append({**c, "configurado": bool(v),
                       "valor": (enmascarar(v) if c["secreto"] else v) if v else ""})
    return {"editable": editable, "campos": campos}


def validar(cambios: dict[str, str]) -> dict[str, str]:
    """Limpia lo que llega del formulario y rechaza claves no permitidas."""
    limpio = {}
    for clave, valor in cambios.items():
        if clave not in PERMITIDAS:
            raise ValueError(f"No se puede cambiar {clave} desde el panel")
        valor = str(valor).strip().strip('"').strip("'")
        if re.search(r"[\r\n]", valor):
            raise ValueError("El valor no puede tener saltos de línea")
        limpio[clave] = valor
    return limpio


def aplicar(cambios: dict[str, str]) -> None:
    guardar_en_env(validar(cambios))
