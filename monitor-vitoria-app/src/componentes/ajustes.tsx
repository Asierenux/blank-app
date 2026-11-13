/** Ajustes: claves (guardadas cifradas en el iPhone), alertas, umbrales y estado de las fuentes. */
import { useState } from "react";
import { Alert, Linking, Pressable, Switch, Text, TextInput, View } from "react-native";

import { Aviso, Etiqueta, Fila, Insignia, Pantalla, Seccion, Tarjeta } from "./ui";
import { useDatos } from "../datos";
import { UMBRALES_DEFECTO, type Umbrales } from "../lib/config";
import { hace } from "../lib/formato";
import { VERSION_APP } from "../lib/version";
import type { Fuente } from "../lib/motor";
import { useColores } from "../lib/tema";
import type { Claves } from "../lib/tipos";

function CampoClave({ titulo, campo, ayuda, url, multilinea, placeholder }: {
  titulo: string; campo: keyof Claves; ayuda: string; url?: string; multilinea?: boolean; placeholder: string;
}) {
  const c = useColores();
  const { claves, ponerClave } = useDatos();
  const [texto, setTexto] = useState("");
  const [editando, setEditando] = useState(false);
  const guardada = !!claves[campo];
  return (
    <View style={{ gap: 8, paddingVertical: 6 }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
        <Text style={{ color: c.texto, fontSize: 16, fontWeight: "600" }}>{titulo}</Text>
        {guardada ? <Insignia nivel="ok" texto="Guardada" /> : <Insignia nivel="aviso" texto="Falta" />}
      </View>
      <Etiqueta>{ayuda}</Etiqueta>
      {editando ? (
        <>
          <TextInput value={texto} onChangeText={setTexto} placeholder={placeholder} placeholderTextColor={c.tenue}
            autoCapitalize="none" autoCorrect={false} secureTextEntry={!multilinea && campo !== "euskalmetEmail"}
            multiline={multilinea} keyboardType={campo === "euskalmetEmail" ? "email-address" : "default"}
            style={{ color: c.texto, backgroundColor: c.tarjetaAlta, borderRadius: 12, padding: 12, fontSize: 14,
              minHeight: multilinea ? 120 : undefined, fontFamily: multilinea ? "Menlo" : undefined }} />
          <View style={{ flexDirection: "row", gap: 10 }}>
            <Boton texto="Guardar" onPress={async () => { await ponerClave(campo, texto); setTexto(""); setEditando(false); }} />
            <Boton texto="Cancelar" secundario onPress={() => { setTexto(""); setEditando(false); }} />
          </View>
        </>
      ) : (
        <View style={{ flexDirection: "row", gap: 10, flexWrap: "wrap" }}>
          <Boton texto={guardada ? "Cambiar" : "Añadir"} onPress={() => setEditando(true)} />
          {guardada && <Boton texto="Borrar" secundario onPress={() => ponerClave(campo, "")} />}
          {url && <Boton texto="Conseguir clave ↗" secundario onPress={() => Linking.openURL(url)} />}
        </View>
      )}
    </View>
  );
}

function Boton({ texto, onPress, secundario }: { texto: string; onPress: () => void; secundario?: boolean }) {
  const c = useColores();
  return (
    <Pressable onPress={onPress} style={({ pressed }) => ({ paddingHorizontal: 14, paddingVertical: 9, borderRadius: 10,
      backgroundColor: secundario ? c.tarjetaAlta : c.acento, opacity: pressed ? 0.7 : 1 })}>
      <Text style={{ color: secundario ? c.texto : "#fff", fontWeight: "600" }}>{texto}</Text>
    </Pressable>
  );
}

const CAMPOS_UMBRAL: [keyof Umbrales, string, string][] = [
  ["tempMax", "Calor extremo", "°C"],
  ["tempMin", "Helada fuerte", "°C"],
  ["rachaMs", "Racha de viento", "m/s"],
  ["aqiMax", "Aire malo", "AQI"],
  ["pvpcBarato", "Luz barata por debajo de", "€/kWh"],
  ["embalsePct", "Embalse casi lleno", "%"],
  ["crecidaFactor", "Crecida (veces lo normal)", "×"],
];

function CampoUmbral({ campo, titulo, unidad }: { campo: keyof Umbrales; titulo: string; unidad: string }) {
  const c = useColores();
  const { preferencias, ponerPreferencias } = useDatos();
  const actual = preferencias.umbrales[campo];
  const [texto, setTexto] = useState(actual == null ? "" : String(actual).replace(".", ","));
  const guardar = () => {
    const limpio = texto.trim().replace(",", ".");
    const valor = limpio === "" ? null : Number(limpio);
    if (valor != null && !Number.isFinite(valor)) {
      setTexto(actual == null ? "" : String(actual).replace(".", ","));
      return;
    }
    void ponerPreferencias({ ...preferencias, umbrales: { ...preferencias.umbrales, [campo]: valor } });
  };
  return (
    <Fila izquierda={titulo} detalle={actual == null ? "Desactivada" : undefined}
      derecha={
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <TextInput value={texto} onChangeText={setTexto} onEndEditing={guardar} keyboardType="numbers-and-punctuation"
            placeholder="—" placeholderTextColor={c.tenue}
            style={{ color: c.texto, backgroundColor: c.tarjetaAlta, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6,
              minWidth: 70, textAlign: "right", fontSize: 15, fontVariant: ["tabular-nums"] }} />
          <Text style={{ color: c.suave, width: 44 }}>{unidad}</Text>
        </View>
      } />
  );
}

/** Ajustes: se abre como hoja desde el engranaje de Inicio. */
export function Ajustes({ cerrar }: { cerrar?: () => void }) {
  const c = useColores();
  const { panel, preferencias, ponerPreferencias, actualizar, actualizando, vaciar } = useDatos();
  return (
    <Pantalla titulo="Ajustes" derecha={cerrar && (
      <Pressable onPress={cerrar} hitSlop={10} style={{ paddingBottom: 8 }}>
        <Text style={{ color: c.acento, fontSize: 17, fontWeight: "600" }}>Listo</Text>
      </Pressable>
    )}>
      <Seccion titulo="Claves de acceso" icono="ajustes">
        <Tarjeta>
          <Etiqueta>Se guardan cifradas en el llavero del iPhone y solo se envían a su propia web.</Etiqueta>
          <CampoClave titulo="AEMET" campo="aemet" placeholder="eyJhbGciOi…" url="https://opendata.aemet.es/centrodedescargas/altaUsuario"
            ayuda="Tiempo en Vitoria. Gratis: te la mandan por correo." />
          <CampoClave titulo="WAQI" campo="waqi" placeholder="Token" url="https://aqicn.org/data-platform/token/"
            ayuda="Calidad del aire. Gratis, llega al momento." />
          <CampoClave titulo="Euskalmet · correo" campo="euskalmetEmail" placeholder="tu@correo.com"
            url="https://opendata.euskadi.eus/api-euskalmet/-/como-utilizar-la-api-de-euskalmet/"
            ayuda="El correo con el que te diste de alta en la API." />
          <CampoClave titulo="Euskalmet · clave privada" campo="euskalmetPem" multilinea
            placeholder={"-----BEGIN PRIVATE KEY-----\n…\n-----END PRIVATE KEY-----"}
            ayuda="Abre el archivo privateKey.pem, copia TODO su texto y pégalo aquí." />
        </Tarjeta>
        <Aviso texto="Sin claves también funcionan: precio de la luz, embalses y ríos, energía, tráfico, autobuses y tranvía." />
      </Seccion>

      <Seccion titulo="Alertas" icono="campana">
        <Tarjeta>
          <Fila izquierda="Notificaciones" detalle="Solo mientras la app se usa: iOS no deja a las apps vigilar sin parar."
            derecha={<Switch value={preferencias.alertas} onValueChange={v => ponerPreferencias({ ...preferencias, alertas: v })} />} />
          <Fila izquierda="☀️ Resumen de las 7:30" detalle="Tiempo, paraguas, luz barata, avisos y agenda. Llega aunque no abras la app."
            derecha={<Switch value={preferencias.resumenDiario} disabled={!preferencias.alertas}
              onValueChange={v => ponerPreferencias({ ...preferencias, resumenDiario: v })} />} />
          <Fila izquierda="💡 Precios de mañana" detalle="Aviso con las mejores horas en cuanto la app ve los precios (desde ~20:15)."
            derecha={<Switch value={preferencias.avisoPrecios} disabled={!preferencias.alertas}
              onValueChange={v => ponerPreferencias({ ...preferencias, avisoPrecios: v })} />} />
          {CAMPOS_UMBRAL.map(([campo, titulo, unidad]) => (
            <CampoUmbral key={campo + String(preferencias.umbrales[campo])} campo={campo} titulo={titulo} unidad={unidad} />
          ))}
          <Etiqueta>Deja un umbral vacío para desactivar esa alerta.</Etiqueta>
          <Boton texto="Volver a los valores por defecto" secundario
            onPress={() => ponerPreferencias({ ...preferencias, umbrales: UMBRALES_DEFECTO })} />
        </Tarjeta>
      </Seccion>

      <Seccion titulo="Fuentes de datos" accion={
        <Pressable onPress={() => actualizar(true)}><Text style={{ color: c.acento, fontSize: 16 }}>{actualizando ? "Actualizando…" : "Actualizar todo"}</Text></Pressable>
      }>
        <Tarjeta>
          {panel?.fuentes.map((f, i, todas) => (
            <Pressable key={f.nombre} onPress={() => actualizar(true, [f.nombre as Fuente])}>
              <Fila ultima={i === todas.length - 1}
                izquierda={f.descripcion}
                detalle={[f.ultimaOk ? `Último dato ${hace(f.ultimaOk)}` : null, f.error].filter(Boolean).join(" · ") || undefined}
                derecha={<Insignia nivel={f.nivel} texto={f.texto} />} />
            </Pressable>
          ))}
          <Etiqueta>Toca una fuente para probarla ahora.</Etiqueta>
        </Tarjeta>
      </Seccion>

      <Seccion titulo="Datos">
        <Tarjeta>
          <Etiqueta>El histórico (hasta un mes) se guarda solo en este iPhone.</Etiqueta>
          <Boton texto="Vaciar histórico" secundario onPress={() => Alert.alert("¿Vaciar el histórico?",
            "Se borran las gráficas guardadas. Las claves y ajustes se mantienen.",
            [{ text: "Cancelar", style: "cancel" }, { text: "Vaciar", style: "destructive", onPress: () => void vaciar() }])} />
        </Tarjeta>
        <Etiqueta>
          Monitor Vitoria · versión del {VERSION_APP} · Datos: AEMET, Euskalmet, WAQI, Red Eléctrica, SAIH Ebro,
          Open Data Euskadi (tráfico y Moveuskadi, CC BY 4.0).
        </Etiqueta>
      </Seccion>
    </Pantalla>
  );
}
