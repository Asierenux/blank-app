import dataclasses
from datetime import datetime, timezone

import pytest

from monitor_vitoria.modelos import ErrorRecolector
from monitor_vitoria.recolectores.aemet import RecolectorAemet
from monitor_vitoria.recolectores.pvpc import RecolectorPvpc
from monitor_vitoria.recolectores.waqi import RecolectorWaqi


def test_aemet_dos_pasos_y_conversion(config, cliente_falso):
    lecturas = RecolectorAemet(config, cliente_falso).recoger()
    # 2 observaciones x 6 métricas
    assert len(lecturas) == 12
    temp = [l for l in lecturas if l.metrica == "temperatura"]
    assert temp[1].valor == 7.9 and temp[1].unidad == "°C"
    assert temp[1].momento == datetime(2026, 10, 31, 8, tzinfo=timezone.utc)


def test_aemet_sin_clave(config, cliente_falso):
    sin_clave = dataclasses.replace(config, aemet_api_key=None)
    assert RecolectorAemet(sin_clave, cliente_falso).falta_configuracion()


def test_pvpc_redata_sin_token(config, cliente_falso):
    lecturas = RecolectorPvpc(config, cliente_falso).recoger()
    assert [l.valor for l in lecturas] == [0.1325, 0.0612]   # €/MWh -> €/kWh
    assert lecturas[0].momento_utc == "2026-10-30T23:00:00Z"  # 00:00 Madrid = 23:00 UTC


def test_pvpc_esios_filtra_peninsula(config, cliente_falso):
    con_token = dataclasses.replace(config, esios_token="tok")
    lecturas = RecolectorPvpc(con_token, cliente_falso).recoger()
    assert [l.valor for l in lecturas] == [0.14, 0.09]


def test_waqi(config, cliente_falso):
    lecturas = {l.metrica: l.valor for l in RecolectorWaqi(config, cliente_falso).recoger()}
    assert lecturas == {"aqi": 34, "pm25": 34, "pm10": 12, "no2": 9.2, "o3": 21}


def test_waqi_error(config, cliente_falso):
    with pytest.raises(ErrorRecolector):
        RecolectorWaqi(config, cliente_falso).parsear({"status": "error", "data": "Invalid key"})
