# Control de Verificación de Carcasas (MDV MAC)

Documentación técnica para quien mantenga esta app — humano o un asistente
de IA (Claude Code u otro) sin memoria de cómo se construyó. El README.md
es para el usuario final (instalación); esto es para quien tenga que
entender o cambiar el código.

## Qué es esto

Digitaliza la MDV (Método De Verificación) de carcasas de Michelin,
sustituyendo a `MDV_MAC.xlsm` (Excel + VBA). Un Operario registra
verificaciones de calidad sobre carcasas fabricadas en máquinas MAC; la app
calcula sola qué tipo de verificación toca, aplica las reglas de la MDV/INS
para escalar o calificar máquinas y dimensiones, y lleva el histórico.

Stack: Python + Streamlit (UI y servidor) + SQLite (toda la base de datos
vive en un único fichero, `data/mdv.db`, no versionado en git).

## Estructura de ficheros

- `streamlit_app.py` — punto de entrada: arranque, autenticación, modo
  consulta remota, navegación entre páginas.
- `db.py` — TODA la lógica de negocio y acceso a datos. Es el fichero más
  importante: el autómata de estados de la MDV vive aquí
  (`procesar_verificacion`, `guia_estado_actual`), junto con el esquema
  SQL, las migraciones (`_migrar_*`), y la integración con Oracle/fugas.
- `ui.py` — helpers visuales reutilizables (paleta, cabeceras, badges,
  gráficos Vega-Lite, marca de agua del logo).
- `views/*.py` — una página de Streamlit por fichero (`st.Page`). Cada una
  es un script que se ejecuta de arriba a abajo en cada interacción (así
  funciona Streamlit): no hay controladores ni rutas, es procedural.
- `oracle_ds.py` — conexión de solo lectura a la base de datos Oracle de
  fabricación (ver más abajo, "Fugas de fabricación").
- `exportar_oracle_ds.py` — script independiente para exportar de Oracle a
  CSV desde OTRO PC (el que tenga acceso a esa red), cuando el PC donde
  corre la app no llega hasta allí.
- `tests/` — scripts de humo con `streamlit.testing.v1.AppTest` (no
  pytest: ejecútalos con `python tests/test_....py`). Cubren el flujo de
  Técnico y el flujo completo de Operario en Registro de verificación.
  Cada uno usa su propia base de datos temporal: no tocan `data/mdv.db`.
  **Ejecútalos antes de dar por buena cualquier cambio.**
- `assets/branding/` — el logo real de la empresa se coloca aquí a mano,
  en cada PC; está excluido de git (ver `.gitignore` y el README de esa
  carpeta) para no subir un logo con derechos a un repo público.
- `.streamlit/secrets.toml` — configuración sensible/local de cada PC
  (credenciales de Oracle, carpeta de red). Nunca se sube a git; hay un
  `secrets.toml.example` documentado como plantilla.

## El autómata de estados (el corazón de la app)

Dos estados independientes por cada combinación máquina + dimensión (la
"malla de gestión"):

- **Estado de MÁQUINA** (`E1`/`E2`/`E3`, en la tabla `maquinas`): un CQ
  NCNA escala TODA la máquina a Tri Dirigido (E2), porque puede afectar a
  cualquier dimensión fabricada en ella.
- **Estado de DIMENSIÓN en esa máquina** (`D0`..`D5`, en `asignaciones`,
  una fila por combinación máquina+dimensión): un CQ que no es NCNA sólo
  escala esa dimensión concreta.

`db.ESTADOS_MAQ` / `db.ESTADOS_DIM` traducen los códigos a texto.
`db.TRANSICIONES_TIPO_VERIFICACION` (la tabla "CONTROL VERIFICACIONES" de
TAB_MAE) dice qué tipo(s) de verificación (`V1`-`V8`) tocan según el cruce
de ambos estados. Toda la lógica de transición vive en
`db.procesar_verificacion()`: se le pasa la asignación actual, el tipo de
verificación, los CQ detectados y la cantidad, y devuelve el nuevo estado,
el comentario para el operario, y si hace falta pedir causa/acción
correctora. `db.registrar_verificacion()` persiste ese resultado.

`db.guia_estado_actual()` es la guía PROACTIVA que ve el Operario al elegir
máquina+dimensión, antes de rellenar nada — repite la misma lógica de
"qué toca hacer ahora" a partir del estado ya guardado, sin depender de
enviar una verificación nueva.

### Reglas concretas ya implementadas (importante para no romperlas)

- **Tri Dirigido de máquina (E2 → E3)**: hacen falta
  `UMBRAL_FIN_TRI_MAQ = 20` unidades CONSECUTIVAS sin encontrar el CQ que
  lo desencadenó (se reinicia si vuelve a aparecer), y el Operario debe
  confirmar explícitamente que se da por concluido (checkbox).
- **Fase de validación / TRI (D0 y D4 → D3 Sondeo)**: implementa el
  apartado 3.1 de la INS (`INS_001_CYT_DOMF_OEU1_VIT_FOR_01`) — un lote de
  `UMBRAL_VALIDACION_UNIDADES` unidades (125 en proceso MAC, 80 en
  BNS.Auto) se acepta si tiene `0` CQ NCNA y máximo `5` otros CQ; si no,
  se rechaza, se reinicia el contador (nunca se arrastran unidades) y toca
  un lote nuevo. Un CQ durante este lote pide causa/acción en el momento
  (no espera al cierre del lote) pero NO escala la máquina a Tri Dirigido
  por sí solo — la INS dice "continuación del TRI". El progreso del lote
  en curso se guarda por asignación (`contador_val_unidades/ncna/h2`) y se
  ve en `guia_estado_actual()`.
- **Matrículas**: siempre 8 dígitos numéricos (`MATRICULA_LONGITUD`),
  únicas (no se repiten entre dimensiones/máquinas) — esto es lo que
  permite, en las fugas de fabricación, localizar en qué verificación
  nuestra cae una matrícula sólo por su número.
- **Sólo carcasas**: se quitó "Bandage" como tipo de producto de toda la
  app (formularios, catálogo de CQ, título). Si algún día vuelve a hacer
  falta, `CQ_NCNA_CARCASA` y `familia_cq()` son el punto de partida.

## La malla máquina × dimensión ("en marcha")

Todas las dimensiones existen en todas las máquinas automáticamente
(`db._crear_asignaciones_faltantes()`, se ejecuta al arrancar y al crear
una máquina/dimensión) — inactivas por defecto. Un Técnico decide cuándo
un código "entra en marcha" (producción) en una máquina concreta, en
**Máquinas y Dimensiones → En marcha y estado**. Sólo las combinaciones
activas:
- aparecen para verificar en Registro de verificación
  (`list_asignaciones(solo_activas=True)`), y
- cuentan por defecto en las estadísticas (Inicio, No Conformidades y
  Causas) — hay un selector "Ámbito de las estadísticas" para ver el
  histórico completo en su lugar.

Eliminar una máquina/dimensión sólo se permite si ninguna de sus
combinaciones está en marcha ni tiene verificaciones registradas
(`maquina_eliminable()` / `dimension_eliminable()`).

## Roles y autenticación

- **Operario**: acceso anónimo por defecto, sin usuario/contraseña
  (`OPERARIO_ANONIMO` en `streamlit_app.py`). Sólo ve Registro de
  verificación e Historial.
- **Técnico**: usuario/contraseña reales (tabla `usuarios`, hash+sal).
  Se accede desde el desplegable "Acceso técnico" del panel lateral. Ve
  todas las páginas. El primer Técnico se crea en un formulario de
  arranque obligatorio si `count_usuarios() == 0`.

## Fugas de fabricación (integración con Oracle)

Cruza los CQ clasificados en la línea de fabricación (base de datos Oracle
"DS", tabla `DS_GRQ2_TC.PDO_F_MATRICULE_CLASIF` en `RFDWVIT0`) contra las
verificaciones propias, para detectar CQ que se escaparon: matrículas que
SÍ caían dentro de un rango que la MDV verificó, pero cuyo CQ no se
detectó. Sólo cuentan los CQ del catálogo propio (tabla `catalogo_cq`) —
los de procesos posteriores no tienen nada que ver con esta MDV. Lógica de
cruce: `db._procesar_clasificaciones_fabricacion()`.

Dos formas de traer los datos (según si el PC donde corre la app llega o
no a la red de Oracle):
- **En vivo**: `oracle_ds.py` + botón "Sincronizar con Oracle" en No
  Conformidades y Causas → Fugas de fabricación. Credenciales en
  `.streamlit/secrets.toml`, sección `[oracle_ds]`.
- **Por fichero**: `exportar_oracle_ds.py` se ejecuta desde OTRO PC con
  acceso a Oracle (p.ej. el mismo desde el que se usa DBeaver), genera un
  CSV, y se sube en la misma pestaña.

Las fugas encontradas se guardan localmente (`fugas_fabricacion`) y se
avisan al Operario al elegir una dimensión con fugas, sin depender de
Oracle en ese flujo.

## Despliegue: un PC por máquina, sin servidor central

Decisión tomada tras descartar varias alternativas (ver historial de
conversación/commits si hace falta el porqué completo):
- Un servidor único centralizado sería lo "correcto" técnicamente, pero
  no hay forma realista de conseguir una VM/servidor interno de IT ni
  acceso de red directo entre los PCs de las máquinas — sólo hay una
  carpeta de red compartida (`O:`, como la del Excel anterior).
- Reescribir en Power Apps/SharePoint se aparcó como proyecto aparte (no
  es este repositorio).

Arquitectura elegida: **cada PC de máquina sigue teniendo su propia app y
su propia base de datos local**, exactamente como hasta ahora. Encima de
eso:

1. **Copia a red** (`db.copiar_base_datos_a_red()`): cada vez que se
   guarda una verificación, se copia (con el backup nativo de SQLite, no
   un copiado de fichero a pelo) la base de datos local a la carpeta
   configurada en `secrets.toml` (`[copia_red] carpeta_destino`), con un
   nombre único por PC (`mdv_<hostname>.db`).
2. **Modo consulta remota** (`Ver en remoto.bat`, variable de entorno
   `MDV_MODO_REMOTO`): la MISMA app, arrancada en otro PC, deja elegir qué
   copia de red abrir y la abre de solo lectura
   (`db.MODO_SOLO_LECTURA` + `get_conn()` con `mode=ro`, sin `init_db()`).
   Mismo código, mismas páginas, mismos usuarios/contraseñas (es la misma
   base de datos, sólo que congelada). Si se intenta guardar algo, se
   captura el `sqlite3.OperationalError` en `streamlit_app.py` y se
   muestra un aviso en vez de un traceback.

### Aplicar cambios desde el modo remoto (implementado)

Desde el modo consulta remota se puede forzar un estado (máquina o
dimensión) o activar/desactivar una combinación en marcha, sin escribir
nunca directamente en la copia (que sigue abierta con `mode=ro`) y sin
sustituir ni comparar bases de datos completas:

1. **Mismos formularios de siempre**: en `views/maquinas_dimensiones.py`
   → pestaña "En marcha y estado", los botones de "Forzar estado
   manualmente" y "Guardar cambios de marcha" comprueban
   `db.MODO_SOLO_LECTURA`. Si es `True`, en vez de escribir llaman a
   `db.crear_solicitud_remota()`.
2. **Solicitud pequeña y estructurada**: `crear_solicitud_remota()` valida
   la acción contra la whitelist `db.SOLICITUD_ACCIONES` (`forzar_estado_maq`,
   `forzar_estado_dim`, `activar_asignacion`, `desactivar_asignacion`) y
   escribe un JSON en `<carpeta_destino>/solicitudes/pendientes/` —
   identifica el objetivo por `maquina_codigo`/`dimension_codigo` (nunca
   por id numérico, que no es portable entre PCs), más el PC destino
   (`db.PC_OBJETIVO_REMOTO`, apuntado por `streamlit_app.py` al elegir de
   qué PC ver la copia), el autor y la fecha.
3. **La máquina real la aplica sola**: `db.aplicar_solicitudes_pendientes()`
   filtra por su propio hostname, revalida de nuevo la acción y los
   códigos contra su base VIVA (nunca se fía a ciegas del fichero), y
   llama a las mismas funciones de siempre (`set_estado_maquina`,
   `set_estado_dimension`, `set_activa_asignacion`). Cada solicitud se
   mueve a `solicitudes/aplicadas/` o `solicitudes/rechazadas/` (con el
   motivo) para no aplicarse dos veces ni desaparecer en silencio.
4. **Se revisa en cada rerun, con throttle**: como la app se queda abierta
   todo el día, `streamlit_app.py` llama a
   `db.revisar_solicitudes_si_toca()` en cada interacción normal (no sólo
   al arrancar); esta función no vuelve a mirar la carpeta de red si no
   han pasado al menos 30s desde la última vez.
5. El modo remoto muestra, justo debajo del selector de PC, cuántos
   cambios están todavía pendientes de aplicar en esa máquina
   (`db.listar_solicitudes_pendientes_para()`).

## Cómo probar cambios

```
python tests/test_regression_tecnico.py
python tests/test_regression_operario.py
```

Para probar visualmente: `streamlit run streamlit_app.py` y usar la app de
verdad en el navegador — los tests de arriba no sustituyen mirarlo con tus
propios ojos, sobre todo para cambios de UI/diseño.

## Ramas de git

- `claude/beautiful-noether-kyp4xa` — rama de trabajo, siempre al día.
- `backup-v1-sin-oracle` — última versión estable antes de la integración
  con Oracle.
- `backup-v2-con-oracle` — justo después de esa integración.

Ninguna de las dos ramas de backup se actualiza: son puntos de retorno
fijos, no ramas activas.
