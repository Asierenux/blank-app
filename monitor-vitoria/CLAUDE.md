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
| `recolectores/saih.py` | SAIH Ebro: embalses (cota, volumen, %, entrada, salida) y ríos (nivel, caudal). **Scraping** tolerante de la web pública (no hay API documentada): regex sobre texto normalizado, exige la unidad tras el número y comprueba que la página sea de la estación (`claves`). Catálogo de estaciones con códigos; `SAIH_CODIGOS` en `.env` los completa. |
| `recolectores/generacion.py` | REData: generación hidráulica diaria (MWh y %) del País Vasco (`geo_limit=ccaa`, `geo_ids=10`) y península. |
| `panel.py` | Interpreta los datos para el panel: nivel ok/aviso/critico de cada indicador, dato antiguo, tendencia 1 h, tramos PVPC (terciles de cada día), mejor franja de 3 h, salud de fuentes y estado global. Pura lógica, testeable. |
| `web/app.py` | FastAPI: `/` (esqueleto HTML), `/api/panel` (todo lo de `panel.py`), `/api/ultimas`, `/api/serie/{fuente}/{metrica}`, `/api/ejecuciones`, `/salud`, `/docs`. |
| `web/templates/index.html` + `web/static/` | Panel por pestañas: solo pinta. Pide `/api/panel` cada 60 s (y `/api/agua/historico` en Agua). Chart.js + sparklines SVG propios. |
| `demo.py` | `python -m monitor_vitoria demo` → `datos/demo.db` con datos simulados. |
| `__main__.py` | CLI: `init-db`, `recoger [fuente]`, `planificador`, `web`, `probar-telegram`, `estado`. |

## Base de datos (SQLite, `datos/monitor.db`)

- `lecturas` — formato largo. `UNIQUE(fuente, metrica, momento)`; se inserta con
  `INSERT OR IGNORE`, así repetir una consulta es idempotente.
- `ejecuciones` — una fila por ejecución de un recolector (ok, nuevas, error).
- `alertas_enviadas` — PK `(regla, momento)` para no repetir alertas.

## Agua: qué se puede y qué no se puede saber

- Embalses del Zadorra (Ullíbarri-Gamboa, Urrunaga) y ríos: **SAIH Ebro**, cada 15 min.
  `E028` = Urrunaga (comprobado). Ullíbarri y aforos del Zadorra: **códigos pendientes** (rellenar en `.env`
  y validar con `python -m monitor_vitoria probar-saih CODIGO --estacion id`).
- **Compuertas**: no es dato público. `panel.maniobra()` lo estima con salida vs entrada
  (Desembalsando / Almacenando / Equilibrio). No presentarlo nunca como dato real de compuertas.
- **Producción de cada presa**: no es pública. Se usa la hidráulica total del País Vasco (REE).
- Crecidas: relativas (caudal > `ALERTA_CRECIDA_FACTOR` × mediana 7 días y ≥ 5 m³/s), además de
  umbrales absolutos por estación si se rellenan `caudal_aviso/alerta` en el catálogo.
- `/api/agua/historico?dias=N`: lluvia (AEMET) + % embalses + caudal ríos alineados (≤3 días por horas; más, por días).

## Panel de operaciones (criterios de diseño)

- Pensado como pantalla fija de sala de control: tema oscuro por defecto (botón para claro),
  números grandes con cifras tabulares, todo visible sin scroll en 1080p.
- **Semáforo**: verde `ok`, ámbar `aviso`, rojo `critico`, azul `info` (sin umbral), gris `sin_datos`.
  El color va SIEMPRE acompañado de texto e icono (✓ ▲ ✖) — no depender solo del color.
- **Las reglas de color viven en `panel.py`**, nunca en el JS. El HTML no decide nada.
- El precio de la luz no afecta al estado global (caro ≠ avería). Sí lo hacen las fuentes caídas
  y los datos antiguos.
- Fuente "Caída" = sin éxito en 4× su intervalo; "Retrasada" = 2×.
- Se actualiza por `fetch` sin recargar; si el servidor no responde sale una franja roja.
- **Pestañas**: Resumen · Agua · Energía · Aire · Meteo · Sistema (`#agua` en la URL). Cada pestaña lleva un
  punto con su peor estado (`pestanas` en `/api/panel`). Solo se dibujan las gráficas de la pestaña visible.
- Modo pared: `?rotar=20` o botón ⟳ (cambia de pestaña cada N s).
- Frontend en `web/static/panel.js` + `panel.css`; `index.html` es solo estructura.

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
| SAIH Ebro | `www.saihebro.com/tiempo-real/estacion-{embalses|aforos}-{codigo}-{slug}` | ninguna | Sin API: scraping. URL y patrones sin verificar en vivo salvo E028. |
| REData generación | `apidatos.ree.es/es/datos/generacion/estructura-generacion` | ninguna | `time_trunc=day`; serie `type` "Hidráulica". |
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
python -m monitor_vitoria demo && python -m monitor_vitoria web --demo
pytest
```

Los tests no usan red: `httpx.MockTransport` sirve los JSON de `tests/datos/`.
