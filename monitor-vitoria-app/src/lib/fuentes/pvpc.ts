/**
 * Precio PVPC de la luz (Red Eléctrica, API pública REData, sin clave).
 * Se piden hoy y mañana (los de mañana salen hacia las 20:15). Se guarda en €/kWh.
 */
import { fechaMadrid, inicioDiaMadrid } from "../formato";
import { ErrorFuente, type Descargar } from "../tipos";
import { bajarJson, lectura, query, redondear, type Resultado } from "./comun";

const URL = "https://apidatos.ree.es/es/datos/mercados/precios-mercados-tiempo-real";

export function parsearRedata(datos: any) {
  for (const serie of datos?.included ?? []) {
    if (String(serie?.type ?? "").startsWith("PVPC")) {
      return (serie.attributes?.values ?? []).map((v: any) =>
        lectura("pvpc", "precio", Date.parse(v.datetime), redondear(v.value / 1000), "€/kWh"));
    }
  }
  throw new ErrorFuente("REData no devolvió la serie PVPC");
}

export async function recogerPvpc(descargar: Descargar, ahora = Date.now()): Promise<Resultado> {
  const hoy = inicioDiaMadrid(ahora);
  const manana = inicioDiaMadrid(hoy + 36 * 3600e3);
  const url = URL + query({
    start_date: `${fechaMadrid(hoy)}T00:00`,
    end_date: `${fechaMadrid(manana)}T23:59`,
    time_trunc: "hour",
  });
  return { lecturas: parsearRedata(await bajarJson(descargar, url)) };
}
