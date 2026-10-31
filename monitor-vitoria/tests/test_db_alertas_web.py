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
    assert "/api/panel" in cliente.get("/").text   # la página pide los datos por JS
    panel = cliente.get("/api/panel").json()
    temp = next(i for i in panel["indicadores"] if i["id"] == "aemet.temperatura")
    assert temp["valor"] == 12.5 and temp["nivel"] == "ok"
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


# --- Panel de operaciones --------------------------------------------------

def test_niveles(config):
    from monitor_vitoria import panel
    assert panel.nivel_temperatura(36, config)[0] == "critico"
    assert panel.nivel_temperatura(-1, config) == ("aviso", "Helada")
    assert panel.nivel_temperatura(15, config)[0] == "ok"
    assert panel.nivel_racha(21, config)[0] == "critico"
    assert panel.nivel_aqi(72, config) == ("aviso", "Moderado")
    assert panel.nivel_aqi(120, config)[0] == "critico"


def test_pvpc_tramos_y_mejor_franja(config):
    from monitor_vitoria import panel
    conn = db.conectar(config.db_path)
    hoy = AHORA.astimezone(panel.MADRID).replace(hour=0)
    precios = [0.20] * 24
    precios[13:16] = [0.05, 0.06, 0.05]       # franja barata a mediodía
    db.guardar_lecturas(conn, [Lectura("pvpc", "precio", hoy + timedelta(hours=h), v, "€/kWh")
                               for h, v in enumerate(precios)])
    p = panel.construir_pvpc(conn, hoy + timedelta(hours=8, minutes=30))
    assert p["actual"]["v"] == 0.20
    assert p["mejor_franja"]["inicio"] == Lectura("pvpc", "precio", hoy + timedelta(hours=13), 0, "").momento_utc
    assert {x["tramo"] for x in p["puntos"][13:16]} == {"barato"}
    assert p["hay_manana"] is False


def test_fuente_caida_y_global(config):
    from monitor_vitoria import panel
    conn = db.conectar(config.db_path)
    ayer = (AHORA - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with conn:  # último éxito hace 24 h y después un fallo
        conn.execute("INSERT INTO ejecuciones (fuente, inicio, fin, ok) VALUES ('waqi', ?, ?, 1)",
                     (ayer, ayer))
    db.registrar_ejecucion(conn, "waqi", AHORA, ok=False, error="timeout")
    datos = panel.construir_panel(conn, config)
    waqi = next(f for f in datos["fuentes"] if f["nombre"] == "waqi")
    assert waqi["nivel"] == "critico" and waqi["texto"] == "Caída"
    assert datos["estado_global"]["nivel"] == "critico"


def test_api_panel_con_demo(config, monkeypatch, tmp_path):
    import dataclasses

    from monitor_vitoria.demo import generar
    from monitor_vitoria.web import app as modulo_web
    demo = dataclasses.replace(config, db_path=tmp_path / "demo.db")
    generar(demo.db_path)
    monkeypatch.setattr(modulo_web, "config", demo)
    d = TestClient(modulo_web.app).get("/api/panel").json()
    temp = next(i for i in d["indicadores"] if i["id"] == "aemet.temperatura")
    assert temp["valor"] is not None and len(temp["serie"]) > 10
    assert d["pvpc"]["mejor_franja"] and d["pvpc"]["hay_manana"]
    assert len(d["alertas"]) == 4
