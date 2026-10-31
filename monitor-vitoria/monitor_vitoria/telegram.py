"""Envío de mensajes por Telegram.

La API de bots de Telegram es una simple petición HTTP:
    POST https://api.telegram.org/bot<TOKEN>/sendMessage
    {"chat_id": ..., "text": ...}

Si Telegram no está configurado, el mensaje se escribe en el log en vez de
enviarse. Así puedes probar las alertas sin tener todavía un bot.
"""

from __future__ import annotations

import logging

import httpx

from .config import Config

log = logging.getLogger(__name__)


def enviar(config: Config, texto: str, cliente: httpx.Client | None = None) -> bool:
    if not config.telegram_activo:
        log.warning("[Telegram desactivado] %s", texto)
        return False

    url = f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage"
    datos = {"chat_id": config.telegram_chat_id, "text": texto}
    try:
        if cliente is None:
            r = httpx.post(url, json=datos, timeout=15)
        else:
            r = cliente.post(url, json=datos)
        r.raise_for_status()
        return True
    except httpx.HTTPError as e:
        # No imprimimos la URL: contiene el token del bot.
        log.error("No se pudo enviar el mensaje de Telegram: %s", type(e).__name__)
        return False
