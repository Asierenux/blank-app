"""Relevo del SAIH para el iPhone: lectura de la ficha real y fusión del histórico de 7 días."""

import json
from pathlib import Path

from monitor_vitoria import relevo_saih
from monitor_vitoria.recolectores.saih import CATALOGO

DATOS = Path(__file__).parent / "datos"
URRUNAGA = next(e for e in CATALOGO if e.id == "urrunaga")


def test_fusiona_sin_duplicar_y_olvida_lo_viejo():
    t = 1_800_000_000_000
    anterior = {"estaciones": {"urrunaga": {"series": {"nivel": [[t - 3_600_000, 541.9], [t, 541.0], [t - 30 * 86_400_000, 1]]}}}}
    r = relevo_saih.fusionar(anterior, {"urrunaga": {"nivel": [[t, 541.95]], "porcentaje": [[t, 54.27]]}}, t)
    assert r["urrunaga"]["series"]["nivel"] == [[t - 3_600_000, 541.9], [t, 541.95]]   # el nuevo sustituye; lo de hace 30 días, fuera
    assert r["urrunaga"]["series"]["porcentaje"] == [[t, 54.27]]
    assert r["urrunaga"]["codigo"] == "E028"


def test_relevo_completo_sin_red(tmp_path, monkeypatch):
    pagina = (DATOS / "saih_urrunaga_real.html").read_text(encoding="utf-8")
    monkeypatch.setattr(relevo_saih, "contexto", lambda: (object(), "prueba"))

    def descargar(ctx, url):
        if "E028" in url:
            return pagina
        raise OSError("sin red en los tests")
    monkeypatch.setattr(relevo_saih, "descargar", descargar)
    salida = tmp_path / "saih.json"
    assert relevo_saih.main(str(tmp_path / "no-existe.json"), str(salida)) == 0
    d = json.loads(salida.read_text(encoding="utf-8"))
    serie = d["estaciones"]["urrunaga"]["series"]
    assert serie["nivel"][-1][1] == 541.95 and serie["porcentaje"][-1][1] == 54.27
    assert len(d["errores"]) == 2          # Ullíbarri y Mendivil (sin red) no impiden publicar Urrunaga
