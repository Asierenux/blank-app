from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from monitor_vitoria import alertas, db
from monitor_vitoria.modelos import Lectura

AHORA = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)


def lectura(metrica="temperatura", valor=10.0, fuente="aemet", horas=0, unidad="°C"):
    return Lectura(fuente, metrica, AHORA - timedelta(hours=horas), valor, unidad)


def test_guardar_no_duplica(config):
    conn = db.conectar(config.db_path)
    assert len(db.guardar_lecturas(conn, [lectura()])) == 1
    assert len(db.guardar_lecturas(conn, [lectura()])) == 0   # repetida: se ignora
    assert conn.execute("SELECT COUNT(*) FROM lecturas").fetchone()[0] == 1


def test_reglas_y_antiguedad(config):
    reglas = alertas.construir_reglas(config)  # temp_max = 35 por defecto
    disparadas = alertas.evaluar(reglas, [
        lectura(valor=36),            # dispara
        lectura(valor=37, horas=10),  # demasiado antigua: no dispara
        lectura(valor=20),            # normal
    ])
    [(regla, ls)] = disparadas.items()
    assert regla.id == "temp_max" and [l.valor for l in ls] == [36]


def test_alerta_no_se_repite(config):
    conn = db.conectar(config.db_path)
    calor = [lectura(valor=40)]
    assert alertas.procesar(conn, config, calor) == 1
    assert alertas.procesar(conn, config, calor) == 0


def test_umbral_vacio_desactiva_regla(config):
    import dataclasses
    sin = dataclasses.replace(config, alerta_temp_max=None)
    assert "temp_max" not in {r.id for r in alertas.construir_reglas(sin)}


def test_panel_web(config, monkeypatch):
    from monitor_vitoria.web import app as modulo_web
    monkeypatch.setattr(modulo_web, "config", config)
    conn = db.conectar(config.db_path)
    db.guardar_lecturas(conn, [lectura(valor=12.5)])

    cliente = TestClient(modulo_web.app)
    assert cliente.get("/salud").json() == {"ok": True}
    html = cliente.get("/").text
    assert "Temperatura" in html and "12.5" in html
    serie = cliente.get("/api/serie/aemet/temperatura").json()
    assert serie["puntos"][0]["v"] == 12.5
    assert cliente.get("/api/serie/nada/x").status_code == 404


def test_flujo_completo(config, cliente_falso, monkeypatch):
    """recoger -> guardar -> registrar ejecución, con las APIs simuladas."""
    import httpx

    from monitor_vitoria import servicio
    # servicio abre su propio cliente con "with"; le damos uno nuevo con el mismo transporte falso
    monkeypatch.setattr(servicio, "crear_cliente",
                        lambda: httpx.Client(transport=cliente_falso._transport))
    assert servicio.ejecutar_recolector(config, "waqi")
    conn = db.conectar(config.db_path)
    [ejec] = db.ultimas_ejecuciones(conn)
    assert ejec["ok"] == 1 and ejec["nuevas"] == 5
