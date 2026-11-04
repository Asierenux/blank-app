"""Generación automática del modelo 3D con Claude, con reparación y verificación visual.

Flujo:
 1. Claude recibe las fotos (originales y anotadas), el análisis y las medidas reales, y devuelve
    un `Diseno` declarativo (sin código ejecutable).
 2. La app lo valida y construye. Si hay errores, se los devuelve a Claude para que los corrija.
 3. Si se construye, la app renderiza 4 vistas y calcula un informe numérico (tamaños, cuerpos,
    voladizos, comprobaciones). Claude lo compara con las fotos y las medidas y corrige o aprueba.
 4. Solo se da por verificado si Claude aprueba SIN cambios una versión que ya ha visto renderizada
    y todas las comprobaciones numéricas pasan.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Callable

from PIL import Image

from . import asesor, render
from .diseno import REFERENCIA_OPS, Diseno, DisenoError, Resultado, evaluar_diseno, informe_texto

MODEL = asesor.MODEL
MAX_LLAMADAS = 7

SYSTEM = f"""Eres un ingeniero de diseño mecánico experto en CAD paramétrico e impresión 3D FDM.
Diseñas piezas para una Bambu Lab P2S (volumen 256×256×256 mm, boquilla 0.4 mm) a partir de fotos y
medidas reales tomadas con calibre. El objetivo es que la pieza impresa sea IDÉNTICA en lo funcional a la
original (o que resuelva exactamente el problema descrito) y que encaje a la primera.

Describes la pieza como un diseño declarativo: una lista ordenada de nodos (operaciones) que la app
construye con un motor CSG robusto. No escribes código. Cada valor numérico es un número o una
expresión aritmética sobre los parámetros (+ - * / ** %, paréntesis, sqrt, abs, min, max, round, floor,
ceil, hypot, sin/cos/tan/asin/acos/atan/atan2 en GRADOS, pi).

OPERACIONES DISPONIBLES (argumentos entre corchetes son opcionales):
{REFERENCIA_OPS}
REGLAS DEL FORMATO
- Cada nodo tiene un id único y solo puede usar como entradas nodos definidos ANTES.
- Usa solo los argumentos listados para cada operación. 'puntos' va vacío salvo en extruir_poligono/revolucion.
- 'partes' indica qué nodos son piezas finales a imprimir (normalmente una). La app apoya cada parte en
  Z=0 y las separa en X automáticamente, pero la ORIENTACIÓN de impresión la decides tú con 'rotar'.
- Para agujeros pasantes, haz el cilindro más largo que el material (p. ej. h = grosor + 2, desplazado -1 en Z)
  para que la resta sea limpia; nunca dejes caras coplanares en una resta.
- Las uniones deben solaparse ligeramente (0.01–0.1 mm) o compartir volumen para no dejar cuerpos sueltos.

REGLAS DE DISEÑO
- Crea un parámetro por cada medida relevante. Si procede de la ficha, pon su medida_numero y usa EXACTAMENTE
  el valor medido: la app sustituirá siempre el valor por la medida real del usuario.
- Las holguras van en parámetros aparte (p. ej. holgura_agujero) y se aplican en las expresiones, nunca
  alterando el valor medido. Holguras FDM con boquilla 0.4: encaje a presión 0.1, deslizante 0.2,
  holgado 0.3 (por lado en ajustes de cajas/tapas; en diámetro para agujeros). Agujero para tornillo
  M2→2.4, M2.5→2.9, M3→3.4, M4→4.4, M5→5.5, M6→6.5 mm. Agujero para eje/pasador de Ø d → d + 0.2–0.3.
  Si la pieza ENCAJA SOBRE otra (hueco interior), el hueco es medida + holgura; si encaja DENTRO de otra,
  la pieza es medida − holgura.
- Si una medida no está tomada, estímala de forma coherente con las fotos, la referencia de escala y las
  otras medidas, y anótalo en 'supuestos'.
- Paredes ≥ 1.2 mm (mejor ≥ 2 mm en piezas que trabajan). Detalles ≥ 0.8 mm.
- Orienta la pieza para imprimir: cara plana más grande abajo, mínimos voladizos > 45º, y que las capas no
  trabajen a tracción en las zonas que soportan esfuerzo (clips, ganchos, pestañas elásticas).
  Puentes horizontales hasta ~10 mm son aceptables sin soportes.
- Redondea aristas cuando la original las tenga (caja_redondeada, radio_esquinas, revolucion).
- Construye la pieza directamente en su orientación de impresión siempre que puedas (evita rotar al final).
- Añade 'comprobaciones' (la app las verifica geométricamente y te informa):
  · Cotas exteriores clave: ancho_x / fondo_y / alto_z de la pieza tal como queda orientada para imprimir, y
    num_cuerpos = 1. 'esperado' es una expresión de parámetros; punto_x/y/z = "".
  · Sondas solido_en / vacio_en con un punto (punto_x/y/z, expresiones en el sistema de coordenadas de TU
    diseño, antes de que la app la apoye en la cama; esperado = ""): pon una vacio_en en el centro de CADA
    agujero, ranura o hueco (a media profundidad y también cerca del fondo si debe ser pasante), y solido_en
    en zonas que deben ser material (paredes, entre agujeros, nervios). Así se detectan agujeros desplazados,
    no pasantes o paredes que desaparecen.
- Tipos habituales: piezas de revolución (pomos, tapones, casquillos, ruedas) → 'revolucion' con el perfil
  medio; placas/soportes/escuadras → cajas + restas; contornos irregulares vistos desde arriba →
  'extruir_poligono'; clips y ganchos → perfil lateral con 'extruir_poligono' y luego dar el ancho.

EJEMPLO (placa 60×30×4 con dos agujeros M4 y comprobaciones; resumen de nodos):
  parámetros: largo=60 (medida 1), ancho=30, grosor=4, d_tornillo=4 (medida 2), holgura=0.4, margen=8
  base: caja x=largo y=ancho z=grosor
  ag: cilindro h="grosor+2" d="d_tornillo+holgura"
  ag_m: mover [ag] x="-largo/2+margen" z=-1
  ags: array_lineal [ag_m] n=2 dx="largo-2*margen"
  pieza: restar [base, ags]
  partes: placa ← pieza
  comprobaciones: ancho_x="largo" ±0.05; alto_z="grosor" ±0.05; num_cuerpos="1" ±0;
    vacio_en (-largo/2+margen, 0, grosor/2); vacio_en (largo/2-margen, 0, 0.2); solido_en (0, 0, grosor/2)
- No inventes detalles que no se ven; reproduce fielmente los que sí se ven (nervios, rebajes, chaflanes,
  pestañas, avellanados).

REVISIÓN
Tras cada versión que se construya, recibirás 6 vistas renderizadas (incluidos inferior y corte) y un informe numérico. Compáralo
minuciosamente con las fotos y la ficha: forma general, proporciones, número y posición de agujeros,
grosores, orientación, comprobaciones. Si algo no coincide o puede mejorar el encaje o la imprimibilidad,
corrige y devuelve el diseño COMPLETO con aprobado=false y lista los cambios en cambios_realizados.
Solo cuando la versión renderizada sea correcta, devuelve exactamente el mismo diseño con aprobado=true.
Responde siempre en español."""


@dataclass
class Sesion:
    medidas: dict[int, float]
    mensajes: list = field(default_factory=list)
    diseno: Diseno | None = None
    resultado: Resultado | None = None
    render_png: bytes | None = None
    verificado: bool = False
    log: list[str] = field(default_factory=list)
    llamadas: int = 0
    _ultimo_renderizado: dict | None = None


Progreso = Callable[[str], None]


def _cliente(api_key: str | None):
    import anthropic

    return anthropic.Anthropic(api_key=api_key, timeout=900) if api_key else anthropic.Anthropic(timeout=900)


def _llamar(client, mensajes: list):
    """Llamada en streaming (las respuestas con razonamiento pueden ser largas)."""
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=64000,
        system=SYSTEM,
        output_config={"effort": "high"},
        cache_control={"type": "ephemeral"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=mensajes,
        output_format=Diseno,
    ) as stream:
        return stream.get_final_message()


def explicar_error(exc: Exception) -> str:
    """Mensaje comprensible para los errores típicos de la API."""
    try:
        import anthropic
    except ImportError:  # pragma: no cover
        return str(exc)
    if isinstance(exc, anthropic.AuthenticationError):
        return "La clave de API no es válida."
    if isinstance(exc, anthropic.PermissionDeniedError):
        return "La clave de API no tiene permiso para usar este modelo."
    if isinstance(exc, anthropic.RateLimitError):
        return "Límite de uso de la API alcanzado. Espera un minuto y vuelve a intentarlo."
    if isinstance(exc, anthropic.BadRequestError):
        msg = str(getattr(exc, "message", exc))
        if "credit" in msg.lower() or "billing" in msg.lower():
            return "La cuenta de la API no tiene saldo. Añade crédito en platform.claude.com."
        return f"Petición rechazada por la API: {msg}"
    if isinstance(exc, anthropic.APITimeoutError):
        return "Claude tardó demasiado en responder. Vuelve a intentarlo."
    if isinstance(exc, anthropic.APIConnectionError):
        return "No hay conexión con la API de Anthropic. Revisa tu conexión a internet."
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code >= 500:
        return "La API de Anthropic tiene un problema temporal. Inténtalo de nuevo en unos minutos."
    return str(exc)


def _bloques(content) -> list:
    """Contenido del asistente para reenviarlo tal cual en el historial (sin el campo local parsed_output)."""
    out = []
    for b in content:
        if hasattr(b, "model_dump"):
            d = b.model_dump(mode="json", exclude_none=True)
            d.pop("parsed_output", None)
            out.append(d)
        else:
            out.append(b)
    return out


def _png_block(png: bytes) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.standard_b64encode(png).decode()}}


def _firma(d: Diseno) -> dict:
    return d.model_dump(exclude={"aprobado", "cambios_realizados"})


def mensaje_inicial(images: list[Image.Image], analisis: asesor.Analisis, valores: dict[int, float | None],
                    objetivo: str) -> dict:
    content: list[dict] = []
    for i, img in enumerate(images):
        content.append({"type": "text", "text": f"Foto {i} original ({img.width}×{img.height} px):"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": asesor._b64_jpeg(img)}})
        if any(m.visible and m.indice_foto == i for m in analisis.medidas):
            content.append({"type": "text", "text": f"Foto {i} con las cotas numeradas de la ficha dibujadas encima:"})
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                        "data": asesor._b64_jpeg(asesor.anotar(img, analisis.medidas, i))}})
    medidas = []
    for m in analisis.medidas:
        v = valores.get(m.numero)
        medidas.append({
            "numero": m.numero, "nombre": m.nombre, "tipo": m.tipo, "donde": m.donde, "critica": m.critica,
            "valor": v if v is not None else m.valor_estimado,
            "origen": "MEDIDO con calibre por el usuario" if v is not None else
                      ("estimado desde la foto (sin medir)" if m.valor_estimado else "SIN DATO: estímalo tú"),
            "unidad": "grados" if m.tipo == "angulo" else "mm",
        })
    ficha = {
        "objetivo_del_usuario": objetivo or "Replicar la pieza de forma idéntica",
        "pieza": analisis.pieza, "descripcion": analisis.descripcion,
        "estrategia_sugerida": analisis.estrategia, "explicacion": analisis.explicacion_estrategia,
        "referencia_escala": analisis.referencia_escala, "material_recomendado": analisis.material_recomendado,
        "medidas": medidas,
    }
    content.append({"type": "text", "text":
                    "FICHA DE LA PIEZA (JSON):\n" + json.dumps(ficha, ensure_ascii=False, indent=1) +
                    "\n\nDiseña el modelo 3D paramétrico completo. Razona primero la geometría pieza a pieza "
                    "(qué volúmenes la forman, qué se resta, dónde va cada agujero respecto a qué referencia), "
                    "luego construye los nodos. aprobado=false en esta primera versión."})
    return {"role": "user", "content": content}


def _bucle(s: Sesion, client, progreso: Progreso, max_llamadas: int) -> Sesion:
    limite = s.llamadas + max_llamadas
    while s.llamadas < limite:
        ronda = s.llamadas + 1
        progreso(f"Ronda {ronda}: Claude está {'diseñando' if s.diseno is None else 'revisando'} el modelo…")
        try:
            resp = _llamar(client, s.mensajes)
        except Exception as exc:  # noqa: BLE001 - errores de red/API
            if s.diseno is None:
                raise RuntimeError(explicar_error(exc)) from exc
            s.log.append(f"Ronda {ronda}: se interrumpió la comunicación con Claude ({explicar_error(exc)}). "
                         "Se conserva la última versión construida.")
            return s
        s.llamadas += 1
        s.mensajes.append({"role": "assistant", "content": _bloques(resp.content)})
        if resp.stop_reason == "refusal":
            raise RuntimeError("Claude no ha podido completar el diseño con esta información.")
        d = getattr(resp, "parsed_output", None)
        if resp.stop_reason == "max_tokens" or d is None:
            s.log.append(f"Ronda {ronda}: respuesta incompleta, se reintenta.")
            s.mensajes.append({"role": "user", "content": "Tu respuesta quedó incompleta o no era un diseño válido. "
                                                          "Devuelve el diseño completo, más compacto si hace falta."})
            continue
        try:
            r = evaluar_diseno(d, medidas=s.medidas)
        except DisenoError as e:
            s.log.append(f"Ronda {ronda}: el diseño tiene {len(e.errores)} error(es); Claude los corrige.")
            progreso(f"Ronda {ronda}: corrigiendo {len(e.errores)} error(es) de construcción…")
            s.mensajes.append({"role": "user", "content":
                               "La app NO pudo construir tu diseño. Errores:\n- " + "\n- ".join(e.errores) +
                               "\nCorrígelos y devuelve el diseño COMPLETO (aprobado=false)."})
            continue

        cambios = "; ".join(d.cambios_realizados) if d.cambios_realizados else ""
        sin_cambios = s._ultimo_renderizado is not None and _firma(d) == s._ultimo_renderizado
        if d.aprobado and sin_cambios and r.comprobaciones_ok:
            s.diseno, s.resultado, s.verificado = d, r, True
            s.log.append(f"Ronda {ronda}: Claude ha revisado el render y aprueba el diseño. ✅")
            return s
        if d.aprobado and not r.comprobaciones_ok:
            s.log.append(f"Ronda {ronda}: Claude lo aprobó pero alguna comprobación numérica falla; se le pide revisarlo.")
        elif d.aprobado and not sin_cambios:
            s.log.append(f"Ronda {ronda}: Claude aprobó con cambios; se verifica de nuevo la versión modificada.")
        else:
            s.log.append(f"Ronda {ronda}: versión construida" + (f" (cambios: {cambios})" if cambios else "") + ".")

        progreso(f"Ronda {ronda}: renderizando vistas para la revisión…")
        png = render.vistas_png(r.meshes, d.nombre)
        s.diseno, s.resultado, s.render_png, s.verificado = d, r, png, False
        s._ultimo_renderizado = _firma(d)
        s.mensajes.append({"role": "user", "content": [
            _png_block(png),
            {"type": "text", "text": informe_texto(d, r) +
             "\n\nEstas son 6 vistas del modelo tal como se imprimirá (incluida la inferior y un corte por el centro para ver el interior). Compáralo con las fotos y la ficha. "
             "Si todo coincide y no hay nada que mejorar, devuelve EXACTAMENTE el mismo diseño con aprobado=true. "
             "Si no, corrige y devuelve el diseño completo con aprobado=false."},
        ]})
    if s.diseno is None:
        raise RuntimeError("No se consiguió un diseño válido tras varios intentos. Revisa las medidas o añade fotos.")
    s.log.append("Se alcanzó el límite de rondas sin aprobación final: revisa el modelo con atención.")
    return s


def generar(images: list[Image.Image], analisis: asesor.Analisis, valores: dict[int, float | None], objetivo: str,
            api_key: str | None = None, client=None, progreso: Progreso | None = None,
            max_llamadas: int = MAX_LLAMADAS) -> Sesion:
    client = client or _cliente(api_key)
    medidas = {k: float(v) for k, v in valores.items() if v is not None}
    s = Sesion(medidas=medidas, mensajes=[mensaje_inicial(images, analisis, valores, objetivo)])
    return _bucle(s, client, progreso or (lambda _m: None), max_llamadas)


def corregir(s: Sesion, comentario: str, api_key: str | None = None, client=None,
             progreso: Progreso | None = None, max_llamadas: int = 4) -> Sesion:
    """El usuario indica qué está mal; Claude corrige y se vuelve a verificar."""
    client = client or _cliente(api_key)
    s.verificado = False
    s.mensajes.append({"role": "user", "content":
                       "CORRECCIÓN DEL USUARIO (tiene la pieza real delante, su indicación tiene prioridad): "
                       + comentario.strip() + "\nAplica la corrección y devuelve el diseño completo con aprobado=false."})
    s._ultimo_renderizado = None
    return _bucle(s, client, progreso or (lambda _m: None), max_llamadas)
