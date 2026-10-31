"""Tests de embalses, ríos, crecidas y generación hidráulica."""
import dataclasses
from datetime import datetime, timedelta, timezone

import pytest

from monitor_vitoria import alertas, db, panel
from monitor_vitoria.modelos import ErrorRecolector, Lectura
from monitor_vitoria.recolectores.generacion import RecolectorGeneracion
from monitor_vitoria.recolectores.saih import (CATALOGO, RecolectorSaih, extraer, normalizar,
                                               numero_es)

from .conftest import DATOS

AHORA = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)


def test_numeros_en_formato_espanol():
    assert numero_es("52,660") == 52.66
    assert numero_es("1.234,5") == 1234.5
    assert numero_es("3.5") == 3.5


def test_saih_recoge_embalse_y_rio(config, cliente_falso):
    lecturas = {l.metrica: l for l in RecolectorSaih(config, cliente_falso).recoger()}
    assert lecturas["urrunaga.nivel"].valor == 543.99
    assert lecturas["urrunaga.volumen"].valor == 52.66
    assert lecturas["urrunaga.porcentaje"].valor == 73.1
    assert lecturas["urrunaga.entrada"].valor == 4.25
    assert lecturas["urrunaga.salida"].valor == 1.8
    assert lecturas["urrunaga.nivel"].momento_utc == "2026-10-31T08:45:00Z"   # 09:45 en Madrid
    assert lecturas["zadorra_arce.caudal"].valor == 38.7
    assert lecturas["zadorra_arce.nivel"].valor == 1.42
    # El <script> con "nivel 1 msnm" no debe confundir al extractor
    assert "1 msnm" not in normalizar((DATOS / "saih_embalse.html").read_text())


def test_saih_codigo_equivocado(config, cliente_falso):
    """Si el código apunta a otra estación, error claro en vez de datos falsos."""
    ullibarri = next(e for e in CATALOGO if e.id == "ullibarri")
    pagina = (DATOS / "saih_embalse.html").read_text()     # es la de Urrunaga
    with pytest.raises(ErrorRecolector, match="código equivocado"):
        RecolectorSaih(config, cliente_falso).parsear(ullibarri, pagina)


def test_saih_porcentaje_calculado_si_falta(config, cliente_falso):
    urrunaga = next(e for e in CATALOGO if e.id == "urrunaga")
    pagina = "<h1>Urrunaga</h1> Volumen 36,0 hm3"
    [l] = [l for l in RecolectorSaih(config, cliente_falso).parsear(urrunaga, pagina)
           if l.metrica.endswith("porcentaje")]
    assert l.valor == 50.0       # 36 de 72 hm³


def test_extraer_tolerante():
    assert extraer(normalizar("Cota del embalse: 540.2 m.s.n.m."), "embalse") == {"nivel": 540.2}


def test_generacion_hidraulica(config, cliente_falso):
    lecturas = RecolectorGeneracion(config, cliente_falso).recoger()
    pv = [l for l in lecturas if l.metrica == "hidraulica_pv"]
    assert [l.valor for l in pv] == [512.4, 845.0]
    assert [l.valor for l in lecturas if l.metrica == "hidraulica_pv_pct"] == [6.1, 9.7]


def _serie_caudal(conn, valores, cada_h=1):
    db.guardar_lecturas(conn, [
        Lectura("saih", "zadorra_arce.caudal", AHORA - timedelta(hours=(len(valores) - i - 1) * cada_h),
                v, "m³/s") for i, v in enumerate(valores)])


def test_crecida_relativa(config):
    conn = db.conectar(config.db_path)
    _serie_caudal(conn, [6.0] * 48)
    pico = Lectura("saih", "zadorra_arce.caudal", AHORA + timedelta(hours=1), 25.0, "m³/s")
    db.guardar_lecturas(conn, [pico])
    [(regla, l, titulo)] = alertas.detectar_crecidas(conn, config, [pico])
    assert regla == "crecida_zadorra_arce" and "x4.2" in titulo
    # y con poco caudal (aunque se triplique) no se avisa
    poco = Lectura("saih", "zadorra_arce.caudal", AHORA + timedelta(hours=2), 4.0, "m³/s")
    assert alertas.detectar_crecidas(conn, config, [poco]) == []


def test_estado_rio_y_embalse(config):
    conn = db.conectar(config.db_path)
    _serie_caudal(conn, [6.0] * 40 + [9, 15, 22, 28])
    rio = next(r for r in panel.construir_agua(conn, config, AHORA)["rios"] if r["id"] == "zadorra_arce")
    assert rio["nivel_estado"] == "critico" and rio["texto"] == "Crecida"
    assert rio["tendencia_3h"] == 19.0

    assert panel.estado_embalse(96, config) == ("critico", "Al máximo · posible vertido")
    assert panel.estado_embalse(88, config)[0] == "aviso"
    assert panel.estado_embalse(60, config) == ("ok", "Normal")
    assert panel.maniobra(2.0, 6.0)["texto"] == "Desembalsando"
    assert panel.maniobra(8.0, 2.0)["texto"] == "Almacenando"
    assert panel.maniobra(None, 3.0) is None


def test_embalse_sin_codigo(config):
    sin = dataclasses.replace(config, saih_codigos={})
    conn = db.conectar(config.db_path)
    ulli = next(e for e in panel.construir_agua(conn, sin, AHORA)["embalses"] if e["id"] == "ullibarri")
    assert ulli["texto"] == "Sin código SAIH"


def test_historico_agua_alinea_lluvia_y_caudal(config):
    conn = db.conectar(config.db_path)
    _serie_caudal(conn, [5, 5, 12, 20])
    db.guardar_lecturas(conn, [Lectura("aemet", "precipitacion", AHORA - timedelta(hours=3), 8.0, "mm")])
    h = panel.historico_agua(conn, config, 1, AHORA + timedelta(minutes=30))
    rio = next(r for r in h["rios"] if r["id"] == "zadorra_arce")
    assert len(h["cubos"]) == len(h["lluvia"]) == len(rio["caudal"])
    assert 8.0 in h["lluvia"] and rio["caudal"][-1] == 20
