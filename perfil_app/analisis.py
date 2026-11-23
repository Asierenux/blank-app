"""Análisis de riesgo de aire ocluido y propuesta de ruletajes para una consigna de neumático.

Se apoya en la geometría de la semisección (neumatico._calcular_plano): las bolsas de aire salen
de que cada producto se apoya sobre los anteriores con cierta rigidez y no entra en los rincones
de los escalones. Aquí se agrupan en zonas de ruletaje, se clasifican por riesgo y se proponen
las pasadas (dónde, ancho de ruleta y sentido para que el aire tenga salida).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from . import neumatico as nm

_f = nm._f


@dataclass
class ZonaRuletaje:
    nombre: str
    x0: float
    x1: float
    area: float                  # mm² de aire en la sección (sin ruletaje)
    alto: float                  # mm, hueco máximo
    area_con_ruletaje: float     # mm² que quedarían tras ruletear
    pares: list[str]             # «debajo → encima»
    riesgo: str                  # ALTO / MEDIO / BAJO
    ancho_ruleta: float          # mm recomendados
    desde: float                 # mm desde el 0 donde empezar la pasada
    hacia: float                 # mm desde el 0 donde terminar (borde libre por donde sale el aire)
    producto_encima: str
    en_aro: bool = False
    volumen_cm3: float = 0.0     # aire por lado (vuelta completa)

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass
class Analisis:
    seccion: str
    zonas: list[ZonaRuletaje]
    bordes_coincidentes: list[tuple[str, float, str, float]]   # (prod, x, prod, x)
    total: float
    total_con_ruletaje: float
    recomendaciones: list[str] = field(default_factory=list)

    def texto(self, cons: nm.ConsignaNeumatico) -> str:
        cab = " · ".join(f"{k}: {cons.cabecera[k]}" for k in ("DIMENSIÓN", "CBL", "C.A.I.") if cons.cabecera.get(k))
        out = [f"ANÁLISIS DE AIRE Y RULETAJES — {self.seccion}", cab, ""]
        out.append(f"Aire estimado entre productos: {_f(round(self.total, 1))} mm² en la sección "
                   f"→ con ruletaje: {_f(round(self.total_con_ruletaje, 1))} mm²")
        out.append("(No se tiene en cuenta el aire de la zona del aro.)")
        out.append("")
        if not self.zonas:
            out.append("No se detectan zonas con aire apreciable con los ajustes actuales.")
        for z in self.zonas:
            sentido = "hacia fuera (hacia el aro)" if z.hacia > z.desde else "hacia el centro (hacia el 0)"
            out.append(f"{z.nombre}  [{z.riesgo}]  de {_f(round(z.x0, 1))} a {_f(round(z.x1, 1))} mm desde el 0"
                       + ("  (zona del aro)" if z.en_aro else ""))
            out.append(f"    Entre: {', '.join(z.pares)}")
            out.append(f"    Aire: {_f(round(z.area, 2))} mm² (hueco máx. {_f(round(z.alto, 2))} mm, "
                       f"≈{_f(round(z.volumen_cm3, 1))} cm³ por lado) → tras ruletear ≈ "
                       f"{_f(round(z.area_con_ruletaje, 2))} mm²")
            if z.en_aro:
                out.append("    Máquina: la ataca el ruletaje de la vuelta (retournement) de la NC, apretando sobre "
                           "el aro y la falaise. El hueco bajo el tramo recto del BT queda cerrado antes de la "
                           "vuelta: depende de que el BT asiente bien sobre el aro y la punta de la falaise al ponerlo.")
            else:
                out.append(f"    Máquina: el rodillo del aplique del {z.producto_encima} tiene que llegar al rincón "
                           f"entre {_f(round(z.x0))} y {_f(round(z.x1))} mm. Si no lo rellena, ese rincón es un canal "
                           f"a lo largo de toda la vuelta: el rodillo empuja el aire (≈{_f(round(z.volumen_cm3, 1))} cm³ "
                           f"por lado) por delante de él y lo deja atrapado en el empalme del {z.producto_encima}, "
                           "a esa cota.")
            out.append("")
        # resumen por máquina: qué zonas toca cada aplique y la pasada final
        por_aplique: dict[str, list] = {}
        for z in self.zonas:
            if not z.en_aro:
                por_aplique.setdefault(z.producto_encima, []).append(z)
        if por_aplique or self.zonas:
            out.append("AJUSTES DE RULETAJE PROPUESTOS (máquina)")
            for prod, zs in por_aplique.items():
                tramos = ", ".join(f"{_f(round(z.x0))}–{_f(round(z.x1))} mm ({z.nombre}, {z.riesgo})"
                                   for z in sorted(zs, key=lambda z: z.x0))
                out.append(f"  • Rodillo del aplique {prod}: presión que llegue al fondo del rincón en {tramos}.")
            criticas = [z for z in self.zonas if not z.en_aro and z.riesgo != "BAJO"]
            if criticas:
                out.append("  • Empalmes a vigilar (donde acaba el aire empujado por el rodillo): "
                           + "; ".join(f"empalme del {z.producto_encima} a {_f(round(z.x0))}–{_f(round(z.x1))} mm "
                                       f"({z.nombre}, ≈{_f(round(z.volumen_cm3, 1))} cm³)" for z in criticas) + ".")
            if any(z.en_aro for z in self.zonas):
                out.append("  • Ruletaje de la vuelta (retournement): presión sobre el aro y la falaise.")
            out.append("")
        if self.bordes_coincidentes:
            out.append("BORDES CASI COINCIDENTES (escalón doble: atrapa aire y cuesta ruletear):")
            for a, xa, b, xb in self.bordes_coincidentes:
                out.append(f"    {a} en {_f(round(xa, 1))} mm  y  {b} en {_f(round(xb, 1))} mm "
                           f"(separados {_f(round(abs(xa - xb), 1))} mm)")
            out.append("")
        out.append("RECOMENDACIONES")
        for i, r in enumerate(self.recomendaciones, 1):
            out.append(f"  {i}. {r}")
        out.append("")
        out.append("Nota: es un modelo geométrico. La forma real de cada perfil (no viene en la consigna), la "
                   "pegajosidad y la temperatura de las gomas cambian los valores absolutos; úsalo para comparar "
                   "zonas y configuraciones, y calíbralo con cortes reales (ajustes de rigidez y chaflán).")
        return "\n".join(out)


def _riesgo(area: float, alto: float) -> str:
    if area >= 2.0 or alto >= 0.8:
        return "ALTO"
    if area >= 0.7 or alto >= 0.4:
        return "MEDIO"
    return "BAJO"


def analizar(cons: nm.ConsignaNeumatico, seccion: str = nm.CARCASA, aj: nm.Ajustes | None = None,
             unir_mm: float = 3.0, minimo: float = 0.2) -> Analisis:
    aj = copy.deepcopy(aj) if aj else nm.Ajustes()
    aj.ruletaje = False
    prods = [p for p in cons.de(seccion) if p.tramos]
    if not prods:
        return Analisis(seccion, [], [], 0.0, 0.0, [])
    info = nm._calcular_plano(cons, prods, aj)[4]
    bolsas = [b for b in info["bolsas"] if b.area >= minimo]
    aj_r = copy.deepcopy(aj)
    aj_r.ruletaje = True
    bolsas_r = nm._calcular_plano(cons, prods, aj_r)[4]["bolsas"]

    # agrupar bolsas cercanas en zonas de ruletaje
    grupos: list[list[nm.Bolsa]] = []
    for b in sorted(bolsas, key=lambda b: b.x0):
        if grupos and b.x0 - max(g.x1 for g in grupos[-1]) <= unir_mm and b.zona_aro == grupos[-1][0].zona_aro:
            grupos[-1].append(b)
        else:
            grupos.append([b])

    tramo = {p.codigo: p.tramos[-1] for p in prods if p.tramos}
    zonas = []
    for g in grupos:
        x0, x1 = min(b.x0 for b in g), max(b.x1 for b in g)
        area = sum(b.area for b in g)
        alto = max(b.alto for b in g)
        resto = sum(br.area for br in bolsas_r if br.x1 >= x0 - 1 and br.x0 <= x1 + 1)
        principal = max(g, key=lambda b: b.area)
        encima = principal.arriba
        # el aire sale por el borde libre más cercano del producto que queda encima
        a, b_ = tramo.get(encima, (x0, x1))
        a = max(a, 0.0)
        xc = (x0 + x1) / 2
        en_aro = any(b.zona_aro for b in g)
        if en_aro:
            # en el aro el producto de encima está vuelto: el aire solo puede salir hacia el flanco
            desde, hacia = x1, x0 - 15
        elif abs(xc - a) <= abs(b_ - xc):
            desde, hacia = x1 + 3, a
        else:
            desde, hacia = x0 - 3, b_
        pares = sorted({f"{b.abajo} → {b.arriba}" for b in g})
        zonas.append(ZonaRuletaje(
            nombre="", x0=x0, x1=x1, area=area, alto=alto, area_con_ruletaje=resto, pares=pares,
            riesgo=_riesgo(area, alto), ancho_ruleta=max(10.0, min(40.0, (x1 - x0) + 6)),
            desde=desde, hacia=hacia, producto_encima=encima, en_aro=en_aro,
            volumen_cm3=sum(b.volumen_cm3 for b in g)))
    orden = {"ALTO": 0, "MEDIO": 1, "BAJO": 2}
    # primero las zonas entre productos (las ataca el rodillo del aplique); la del aro va aparte, al final
    zonas.sort(key=lambda z: (z.en_aro, orden[z.riesgo], -z.area))
    for i, z in enumerate(zonas, 1):
        z.nombre = f"R{i}"

    # bordes casi coincidentes entre productos con cuerpo (≥ 1,5 mm)
    bordes = []
    for p in prods:
        if p.es_aro or not p.tramos or (p.espesor or 0) < 1.5:
            continue
        a, b_ = p.tramos[-1]
        for xe in (a, b_):
            if xe > 0.5:
                bordes.append((p.codigo, xe))
    coinc = []
    for i in range(len(bordes)):
        for j in range(i + 1, len(bordes)):
            (pa, xa), (pb, xb) = bordes[i], bordes[j]
            if pa != pb and abs(xa - xb) < 5.0:
                coinc.append((pa, xa, pb, xb))

    total = sum(b.area for b in info["bolsas"] if not b.zona_aro)
    total_r = sum(b.area for b in bolsas_r if not b.zona_aro)
    # quién encierra el aire (producto de encima con más aire) y valles bajo él entre productos con cuerpo
    por_encima: dict[str, float] = {}
    for b in info["bolsas"]:
        if not b.zona_aro:
            por_encima[b.arriba] = por_encima.get(b.arriba, 0.0) + b.area
    dominante = max(por_encima, key=por_encima.get) if por_encima else None
    valles = []
    if dominante and dominante in tramo:
        a_d, b_d = tramo[dominante]
        cuerpos = sorted((p.tramos[-1] for p in prods if p.tramos and not p.es_aro and p.codigo != dominante
                          and (p.espesor or 0) >= 1.5 and p.tramos[-1][1] > a_d and p.tramos[-1][0] < b_d),
                         key=lambda t: t[0])
        cod_de = {p.tramos[-1]: p.codigo for p in prods if p.tramos}
        fin_max, cod_fin = None, None
        for t in cuerpos:
            if fin_max is not None and t[0] - fin_max > 3:
                valles.append((cod_fin, fin_max, cod_de.get(t, "?"), t[0]))
            if fin_max is None or t[1] > fin_max:
                fin_max, cod_fin = t[1], cod_de.get(t, "?")
    rec = _recomendaciones(cons, prods, zonas, coinc, dominante, por_encima, valles)
    return Analisis(seccion, zonas, coinc, total, total_r, rec)


def _recomendaciones(cons, prods, zonas, coinc, dominante=None, por_encima=None, valles=None) -> list[str]:
    cods = {p.codigo.upper() for p in prods}
    rec = []
    if dominante:
        total = sum(por_encima.values()) or 1.0
        frac = por_encima[dominante] / total * 100
        txt = (f"Quien encierra el aire es sobre todo el {dominante} ({frac:.0f} % del aire entre productos): al "
               "ponerlo, puentea los valles que dejan los productos de debajo y el rodillo no lo lleva hasta el "
               "fondo. Con finales de producto progresivos no es un problema de escalones sino de valles.")
        if valles:
            txt += " Valles bajo el " + dominante + ": " + "; ".join(
                f"entre el final del {a} ({_f(round(xa))} mm) y el inicio del {b} ({_f(round(xb))} mm), "
                f"{_f(round(xb - xa))} mm" for a, xa, b, xb in valles) + "."
        rec.append(txt)
        rec.append(f"Medidas sobre el {dominante}: rodillo del aplique que copie el perfil (segmentado/de discos o "
                   "más blando) con presión en las cotas de las zonas; el producto más caliente y flexible al "
                   "aplicarlo (temperatura de llegada, tiempo de espera) para que se adapte al valle; y, si se puede, "
                   "reducir el valle acercando los productos de debajo (probar el optimizador con más de ±2 mm).")
    altas = [z for z in zonas if z.riesgo == "ALTO" and not z.en_aro]
    if altas:
        rec.append("Prioridad de ruletaje: " + ", ".join(
            f"{z.nombre} ({_f(round(z.x0))}–{_f(round(z.x1))} mm, {', '.join(z.pares)})" for z in altas)
            + ". Son las zonas con más volumen de aire ocluido.")
    rec.append("La puesta es circunferencial: el rodillo del aplique aprieta siempre en las mismas cotas mientras gira "
               "el tambor. Un rincón de escalón que no se rellena es un canal a lo largo de toda la vuelta, y el aire "
               "que hay en él se empuja por delante del rodillo hasta el empalme por superposición, donde queda "
               "atrapado. Por eso las bolsas aparecen sobre todo en el empalme, a la cota de cada zona.")
    rec.append("Rodillo del aplique: que copie el perfil y llegue al fondo de los rincones en las cotas marcadas "
               "(rodillo segmentado o de discos, o más blando, mejor que uno rígido y ancho que puentea el escalón), "
               "con presión suficiente en esas cotas.")
    rec.append("Empalmes: desfasar angularmente los empalmes de productos consecutivos (PS, BJ, PTR, FE) para que "
               "no se acumulen en el mismo punto. El solape lo justo, y los extremos cortados en bisel para que el "
               "empalme no añada otro escalón. Ruletear o apretar el empalme en las cotas de las zonas marcadas y, "
               "si persiste, picar o ventear ahí.")
    if any(z.en_aro for z in zonas):
        rec.append("Zona del aro: la cavidad entre el aro, la pared de la falaise (HF) y el BT, y el rincón donde "
                   "el BJ y el PTR suben sobre la vuelta de la NC, son trampas de aire típicas. Las ataca el "
                   "ruletaje de la vuelta; comprobar también el asiento del aro contra la falaise.")
    if coinc:
        pares = "; ".join(f"{a}/{b} ({_f(round(abs(xa - xb), 1))} mm)" for a, xa, b, xb in coinc)
        rec.append(f"Bordes casi coincidentes: {pares}. Escalonar los bordes al menos 5–10 mm (o usar el "
                   "optimizador ±2 mm) para no sumar dos escalones en el mismo sitio.")
    rec.append("Chaflán de los bordes: cuanto más largo y suave el chaflán de los extremos (PS, BJ, PTR, FE), menos "
               "rincón queda para el aire. Si el perfil lo permite, chaflanes de ángulo bajo (≤ 30°).")
    if "FE" in cods:
        rec.append("El estriado del flanco (FE) ayuda a evacuar el aire hacia fuera al conformar: verificarlo "
                   "(la consigna lo pide: «VERIFICACION ESTRIADO FE»). Si falta o está aplastado, sube el riesgo.")
    rec.append("Pegajosidad (tack) y temperatura: gomas frías, envejecidas o con eflorescencia no se sueldan bien al "
               "ruletear y dejan microbolsas. Respetar los tiempos de reposo/uso y evitar contaminar las caras.")
    rec.append("Si una bolsa persiste en el empalme, revisar con el optimizador si mover 1–2 mm un producto elimina "
               "el escalón que forma el canal: sin rincón no hay canal y no llega aire al empalme.")
    return rec
