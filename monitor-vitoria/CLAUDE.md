# CLAUDE.md — monitor-vitoria

Recoge datos públicos de Vitoria-Gasteiz, los guarda en SQLite, los muestra
en un panel FastAPI y avisa por Telegram cuando se cruzan umbrales.

El usuario está aprendiendo Python: **explica los cambios paso a paso**,
mantén el código sencillo (stdlib primero, sin ORM, sin magia) y comenta
en español el *porqué*, no el *qué*.

## Arquitectura

```
   APIs públicas                 monitor_vitoria/
 ┌──────────────┐   ┌─────────────────────────────────────────────────┐
 │ AEMET        │──▶│ recolectores/aemet.py ─┐                        │
 │ ESIOS/REData │──▶│ recolectores/pvpc.py  ─┼─▶ list[Lectura]        │
 │ WAQI         │──▶│ recolectores/waqi.py  ─┘        │               │
 └──────────────┘   │                                  ▼               │
                    │ planificador.py ──▶ servicio.ejecutar_recolector │
                    │  (APScheduler)        │            │             │
                    │                       ▼            ▼             │
                    │                    db.py ◀──── alertas.py ──▶ telegram.py ──▶ Telegram
                    │                  (SQLite)                         │
                    │                       ▲                           │
                    │ web/app.py (FastAPI) ─┘  solo lectura             │
                    └─────────────────────────────────────────────────┘
```

Dos procesos independientes que comparten el archivo SQLite (modo WAL):
1. `python -m monitor_vitoria planificador` → escribe.
2. `python -m monitor_vitoria web` → lee.

## Módulos

| Archivo | Responsabilidad |
|---|---|
| `config.py` | Lee `.env` → `Config` (dataclass inmutable). Única fuente de configuración. |
| `modelos.py` | `Lectura(fuente, metrica, momento, valor, unidad)` y `ErrorRecolector`. |
| `db.py` | Esquema SQLite + todas las consultas SQL. Nadie más escribe SQL. |
| `recolectores/base.py` | Clase abstracta `Recolector`. |
| `recolectores/{aemet,pvpc,waqi}.py` | Un módulo por fuente. `recoger()` hace red; `parsear*()` es pura. |
| `recolectores/__init__.py` | Registro `RECOLECTORES`. |
| `servicio.py` | Una recogida completa: recolector → `guardar_lecturas` → `registrar_ejecucion` → `alertas.procesar`. Nunca lanza. |
| `planificador.py` | APScheduler (v3, `BlockingScheduler`), un job de intervalo por recolector. |
| `alertas.py` | Reglas construidas desde umbrales del `.env`; dedupe en `alertas_enviadas`. |
| `telegram.py` | `sendMessage`. Sin config → solo log. |
| `web/app.py` | FastAPI: `/` (HTML Jinja2 + Chart.js), `/api/ultimas`, `/api/serie/{fuente}/{metrica}`, `/api/ejecuciones`, `/salud`, `/docs`. |
| `__main__.py` | CLI: `init-db`, `recoger [fuente]`, `planificador`, `web`, `probar-telegram`, `estado`. |

## Base de datos (SQLite, `datos/monitor.db`)

- `lecturas` — formato largo. `UNIQUE(fuente, metrica, momento)`; se inserta con
  `INSERT OR IGNORE`, así repetir una consulta es idempotente.
- `ejecuciones` — una fila por ejecución de un recolector (ok, nuevas, error).
- `alertas_enviadas` — PK `(regla, momento)` para no repetir alertas.

## Convenciones

- **Fechas**: siempre `datetime` con zona horaria; en BD como texto ISO UTC
  (`2026-10-31T08:00:00Z`). Se convierten a Europe/Madrid solo al mostrar.
- **Unidades**: SI / las de la factura. PVPC en €/kWh (la API da €/MWh → `/1000`).
  WAQI guarda sub-índices AQI (escala EE. UU.), no µg/m³.
- **Nombres**: dominio en español (`lectura`, `recolector`, `metrica`).
- **Secretos**: solo en `.env` (ignorado por git). Nunca loguear tokens ni URLs que los contengan.
- **Errores**: un recolector que falla no debe tumbar el planificador; `servicio` captura
  y registra en `ejecuciones`.

## Fuentes

| Fuente | Endpoint | Auth | Notas |
|---|---|---|---|
| AEMET | `opendata.aemet.es/opendata/api/observacion/convencional/datos/estacion/9091R` | cabecera `api_key` | Dos pasos: la respuesta trae una URL `datos`. Datos en ISO-8859-15. 9091R = Vitoria Aeropuerto. |
| PVPC (ESIOS) | `api.esios.ree.es/indicators/1001` | cabecera `x-api-key` | geo 8741 = Península. Mañana se publica ~20:20. |
| PVPC (REData) | `apidatos.ree.es/es/datos/mercados/precios-mercados-tiempo-real` | ninguna | Respaldo si no hay `ESIOS_TOKEN`. Serie `type` que empieza por "PVPC". |
| WAQI | `api.waqi.info/feed/geo:{lat};{lon}/?token=` | query `token` | Estación más cercana. `"-"` = sin dato. |

## Añadir una fuente nueva

1. `recolectores/nueva.py`: subclase de `Recolector` con `nombre`, `descripcion`,
   `metricas`, `intervalo_minutos`, `falta_configuracion()`, `recoger()` y un
   `parsear()` puro.
2. Registrarla en `recolectores/__init__.py`.
3. Variables nuevas → `config.py` **y** `.env.example`.
4. JSON de ejemplo en `tests/datos/`, ruta en `cliente_falso` (`tests/conftest.py`) y test.
5. Reglas de alerta opcionales en `alertas.construir_reglas`.

## Comandos

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python -m monitor_vitoria estado
python -m monitor_vitoria recoger pvpc
python -m monitor_vitoria planificador
python -m monitor_vitoria web --reload
pytest
```

Los tests no usan red: `httpx.MockTransport` sirve los JSON de `tests/datos/`.
