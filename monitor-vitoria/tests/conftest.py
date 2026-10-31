import dataclasses
import json
from pathlib import Path

import httpx
import pytest

from monitor_vitoria.config import cargar_config

DATOS = Path(__file__).parent / "datos"


def cargar_json(nombre: str):
    return json.loads((DATOS / nombre).read_text(encoding="utf-8"))


@pytest.fixture
def config(tmp_path):
    """Configuración de pruebas: base de datos temporal y claves falsas."""
    return dataclasses.replace(
        cargar_config(),
        db_path=tmp_path / "test.db",
        aemet_api_key="clave-falsa",
        esios_token=None,
        waqi_token="token-falso",
        saih_codigos={"urrunaga": "E028", "zadorra_arce": "A0XX"},
        telegram_bot_token=None,
        telegram_chat_id=None,
    )


@pytest.fixture
def cliente_falso():
    """Un httpx.Client que no sale a internet: responde con los JSON de tests/datos."""
    def responder(request: httpx.Request) -> httpx.Response:
        host, ruta = request.url.host, request.url.path
        if host == "opendata.aemet.es" and "/observacion/" in ruta:
            return httpx.Response(200, json={"estado": 200,
                                             "datos": "https://opendata.aemet.es/opendata/sh/x"})
        if host == "opendata.aemet.es" and "/sh/" in ruta:
            texto = (DATOS / "aemet_observacion.json").read_text(encoding="utf-8")
            return httpx.Response(200, content=texto.encode("iso-8859-15"))
        if host == "apidatos.ree.es" and "estructura-generacion" in ruta:
            return httpx.Response(200, json=cargar_json("redata_generacion.json"))
        if host == "apidatos.ree.es":
            return httpx.Response(200, json=cargar_json("redata_pvpc.json"))
        if host == "www.saihebro.com":
            nombre = "saih_embalse.html" if "embalses" in ruta else "saih_aforo.html"
            return httpx.Response(200, text=(DATOS / nombre).read_text(encoding="utf-8"))
        if host == "api.esios.ree.es":
            return httpx.Response(200, json=cargar_json("esios_1001.json"))
        if host == "api.waqi.info":
            return httpx.Response(200, json=cargar_json("waqi_feed.json"))
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(responder)) as c:
        yield c
