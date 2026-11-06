/**
 * Generación hidráulica diaria (REData, sin clave): País Vasco (ccaa 10) y península.
 * Solo días completos (hasta ayer): pedir el día en curso puede dar error 500.
 */
import { fechaMadrid, inicioDiaMadrid } from "../formato";
import { ErrorFuente, type Descargar, type Lectura } from "../tipos";
import { bajarJson, lectura, query, redondear, type Resultado } from "./comun";

const URL = "https://apidatos.ree.es/es/datos/generacion/estructura-generacion";
const ZONAS: Record<string, Record<string, string>> = {
  pv: { geo_trunc: "electric_system", geo_limit: "ccaa", geo_ids: "10" },
  peninsula: {},
};

const RENOVABLES = /hidr[aá]ulica|e[oó]lica|solar|otras renovables|residuos renovables|hidroe[oó]lica|biomasa|biog/i;

/**
 * Parte renovable de cada día: suma de los porcentajes (sobre el total) de las tecnologías
 * renovables. Usa la misma respuesta que la hidráulica, sin pedir nada más.
 */
export function parsearRenovable(datos: any, zona: string): Lectura[] {
  const porDia = new Map<number, number>();
  for (const b of datos?.included ?? []) {
    const nombre = String(b?.attributes?.title ?? b?.type ?? "");
    const tipo = String(b?.attributes?.type ?? "");
    if (/total/i.test(nombre)) continue;
    const renovable = /^renovable/i.test(tipo) || (!/no.?renovable/i.test(tipo) && RENOVABLES.test(nombre));
    if (!renovable) continue;
    for (const v of b.attributes?.values ?? []) {
      if (v?.percentage == null) continue;
      const t = Date.parse(v.datetime);
      porDia.set(t, (porDia.get(t) ?? 0) + v.percentage);
    }
  }
  return [...porDia.entries()].map(([t, p]) => lectura("generacion", `renovable_${zona}_pct`, t, redondear(Math.min(1, p) * 100, 1), "%"));
}

export function parsearGeneracion(datos: any, zona: string): Lectura[] {
  for (const b of datos?.included ?? []) {
    if (String(b?.type ?? "").toLowerCase().startsWith("hidr")) {
      const salida: Lectura[] = [];
      for (const v of b.attributes?.values ?? []) {
        const t = Date.parse(v.datetime);
        salida.push(lectura("generacion", `hidraulica_${zona}`, t, redondear(v.value, 1), "MWh"));
        if (v.percentage != null) {
          salida.push(lectura("generacion", `hidraulica_${zona}_pct`, t, redondear(v.percentage * 100, 2), "%"));
        }
      }
      return salida;
    }
  }
  throw new ErrorFuente(`REData no devolvió la serie Hidráulica (${zona})`);
}

export async function recogerGeneracion(descargar: Descargar, ahora = Date.now()): Promise<Resultado> {
  const hoy = inicioDiaMadrid(ahora);
  const desde = inicioDiaMadrid(hoy - 30 * 86400e3 + 12 * 3600e3);
  const ayer = hoy - 12 * 3600e3;
  const lecturas: Lectura[] = [];
  const errores: string[] = [];
  for (const [zona, extra] of Object.entries(ZONAS)) {
    try {
      const url = URL + query({
        start_date: `${fechaMadrid(desde)}T00:00`, end_date: `${fechaMadrid(ayer)}T23:59`, time_trunc: "day", ...extra,
      });
      const datos = await bajarJson(descargar, url);
      lecturas.push(...parsearGeneracion(datos, zona), ...parsearRenovable(datos, zona));
    } catch (e) {
      errores.push(`${zona}: ${(e as Error).message}`);
    }
  }
  if (errores.length && !lecturas.length) throw new ErrorFuente(errores.join("; "));
  return { lecturas };
}
