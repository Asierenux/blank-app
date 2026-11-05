/**
 * SAIH Ebro a través del relevo de GitHub (ver .github/workflows/relevo-saih.yml).
 *
 * El iPhone no acepta el certificado de www.saihebro.com. GitHub lee el SAIH cada 20 minutos
 * en sus servidores y publica los últimos 7 días en un archivo con certificado válido.
 * Así llegan la cota, el volumen, el llenado, la entrada y la salida de los embalses, y el
 * caudal del Zadorra en Mendivil, como en el programa del ordenador.
 */
import { SENALES } from "../config";
import { ErrorFuente, type Descargar, type Lectura } from "../tipos";
import { bajarJson, lectura, type Resultado } from "./comun";

export const URL_RELEVO = "https://raw.githubusercontent.com/Asierenux/blank-app/datos-saih/saih.json";

/** Los ríos del SAIH se guardan como "hidro.SAIH-<código>" para mostrarlos junto a los de Euskalmet. */
export const idRioSaih = (codigo: string) => `SAIH-${codigo}`;

export interface EstacionSaih { id: string; nombre: string }

export function parsearRelevo(d: any, ahora = Date.now()): Resultado {
  const lecturas: Lectura[] = [];
  const rios: EstacionSaih[] = [];
  for (const [id, e] of Object.entries<any>(d?.estaciones ?? {})) {
    const tipo = e?.tipo === "rio" ? "rio" : "embalse";
    const unidades = SENALES[tipo] as Record<string, readonly [string, string]>;
    const destino = tipo === "rio" ? idRioSaih(e.codigo ?? id) : id;
    if (tipo === "rio") rios.push({ id: destino, nombre: e.nombre ?? id });
    for (const [senal, puntos] of Object.entries<any>(e?.series ?? {})) {
      if (!unidades[senal] || !Array.isArray(puntos)) continue;
      for (const [t, v] of puntos) {
        if (typeof t === "number" && typeof v === "number") {
          lecturas.push(lectura(tipo === "rio" ? "hidro" : "agua", `${destino}.${senal}`, t, v, unidades[senal][1]));
        }
      }
    }
  }
  const errores: string[] = Array.isArray(d?.errores) ? d.errores : [];
  if (!lecturas.length) throw new ErrorFuente(`Relevo del SAIH sin datos${errores.length ? `: ${errores.join("; ")}` : ""}`);
  const generado = Date.parse(d?.generado ?? "");
  const retraso = Number.isFinite(generado) ? Math.round((ahora - generado) / 60000) : null;
  const avisos = [...errores];
  if (retraso != null && retraso > 120) avisos.unshift(`El relevo lleva ${Math.round(retraso / 60)} h sin actualizarse`);
  return { lecturas, extra: { estacionesSaih: rios, avisosSaih: avisos } };
}

export async function recogerSaihRelevo(descargar: Descargar, ahora = Date.now()): Promise<Resultado> {
  // "?t=" evita la copia en caché de hasta 5 min de GitHub; es un archivo estático, no le afecta
  return parsearRelevo(await bajarJson(descargar, `${URL_RELEVO}?t=${Math.floor(ahora / 60000)}`), ahora);
}
