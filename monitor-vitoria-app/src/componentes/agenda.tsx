/** Agenda cultural de Vitoria: tarjeta en Inicio y lista completa con filtros. */
import { useEffect, useMemo, useState } from "react";
import { ActionSheetIOS, Alert, FlatList, Image, Linking, Modal, Platform, Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { fechaMadrid } from "../lib/formato";
import { ocurreEl, type Evento } from "../lib/fuentes/agenda";
import { alfa, useColores } from "../lib/tema";
import { Icono, type NombreIcono } from "./icono";
import { Etiqueta, Tarjeta } from "./ui";

const ICONO: Record<string, NombreIcono> = {
  Concierto: "musica", Teatro: "teatro", Danza: "danza", Exposición: "arte", Cine: "cine", Festival: "fiesta", Conferencia: "micro",
  Formación: "libro", Fiestas: "fiesta", Infantil: "ninos", Bertsolarismo: "charla", Deportes: "deporte",
};
const icono = (tipo: string): NombreIcono => ICONO[tipo] ?? "calendario";

const DIAS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
function etiquetaDia(d: string, hoy: string, manana: string): string {
  if (d === hoy) return "Hoy";
  if (d === manana) return "Mañana";
  const f = new Date(`${d}T12:00:00Z`);
  return `${DIAS[f.getUTCDay()]} ${f.getUTCDate()}`;
}

/** "00:00 - 23:59" (o parecido) = abierto todo el día */
const horario = (e: Evento) => {
  if (!e.hora) return "";
  return /^0?0\s*:\s*00\s*-\s*23\s*:\s*59/.test(e.hora) ? " · todo el día" : ` · ${e.hora.replace(/\s*:\s*/g, ":")}`;
};
const diaCorto = (d: string) => { const f = new Date(`${d}T12:00:00Z`); return `${f.getUTCDate()}/${f.getUTCMonth() + 1}`; };

function abrir(e: Evento) {
  const opciones = [e.entradas && "Comprar entradas", e.url && "Ver información"].filter(Boolean) as string[];
  const ir = (texto: string) => {
    const url = texto === "Comprar entradas" ? e.entradas : e.url;
    if (url) Linking.openURL(url).catch(err => Alert.alert("No se pudo abrir", (err as Error).message));
  };
  if (!opciones.length) return;
  if (opciones.length === 1 || Platform.OS !== "ios") return ir(opciones[0]);
  ActionSheetIOS.showActionSheetWithOptions(
    { title: e.nombre, message: e.descripcion.slice(0, 300), options: [...opciones, "Cancelar"], cancelButtonIndex: opciones.length },
    i => { if (i < opciones.length) ir(opciones[i]); },
  );
}

function FilaEvento({ e, dia }: { e: Evento; dia: string }) {
  const c = useColores();
  return (
    <Pressable onPress={() => abrir(e)} style={({ pressed }) => ({ flexDirection: "row", gap: 12, paddingVertical: 10, opacity: pressed ? 0.6 : 1 })}>
      {e.imagen ? (
        <Image source={{ uri: e.imagen }} style={{ width: 58, height: 58, borderRadius: 12, backgroundColor: c.tarjetaAlta }} />
      ) : (
        <View style={{ width: 58, height: 58, borderRadius: 12, backgroundColor: c.tarjetaAlta, alignItems: "center", justifyContent: "center" }}>
          <Icono n={icono(e.tipo)} color={c.acento} tam={26} />
        </View>
      )}
      <View style={{ flex: 1, gap: 2 }}>
        <Text numberOfLines={2} style={{ color: c.texto, fontSize: 15, fontWeight: "700" }}>{e.nombre}</Text>
        {e.familia && (
          <View style={{ flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start", backgroundColor: alfa(c.ok, 0.14),
            borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 }}>
            <Icono n="ninos" color={c.ok} tam={11} />
            <Text style={{ color: c.ok, fontSize: 11, fontWeight: "800" }}>{e.edad ? `Niños · ${e.edad}` : "Niños y familia"}</Text>
          </View>
        )}
        <View style={{ flexDirection: "row", alignItems: "center", gap: 5 }}>
          <Icono n={icono(e.tipo)} color={c.suave} tam={12} />
          <Text numberOfLines={1} style={{ color: c.suave, fontSize: 13, flex: 1 }}>{e.tipo}{e.lugar ? ` · ${e.lugar}` : ""}</Text>
        </View>
        <Text numberOfLines={1} style={{ color: c.acento, fontSize: 13, fontWeight: "600" }}>
          {dia}{horario(e)}{e.desde !== e.hasta ? ` · hasta el ${diaCorto(e.hasta)}` : ""}{e.precio ? ` · ${e.precio}` : ""}
        </Text>
      </View>
    </Pressable>
  );
}

type Filtro = "hoy" | "manana" | "finde" | "todo";

function AgendaCompleta({ eventos, visible, cerrar, familiaAlAbrir }: {
  eventos: Evento[]; visible: boolean; cerrar: () => void; familiaAlAbrir: boolean;
}) {
  const c = useColores();
  const ins = useSafeAreaInsets();
  const [filtro, setFiltro] = useState<Filtro>("todo");
  const [tipo, setTipo] = useState<string | null>(null);
  const [familia, setFamilia] = useState(familiaAlAbrir);
  useEffect(() => { if (visible) setFamilia(familiaAlAbrir); }, [visible, familiaAlAbrir]);
  const nFamilia = eventos.filter(e => e.familia).length;
  const ahora = Date.now();
  const hoy = fechaMadrid(ahora), manana = fechaMadrid(ahora + 86400e3);
  // Sábado y domingo de esta semana (o los de hoy/mañana si ya es fin de semana)
  const finde = useMemo(() => {
    const dias: string[] = [];
    for (let i = 0; i < 7; i++) {
      const d = fechaMadrid(ahora + i * 86400e3);
      const ds = new Date(`${d}T12:00:00Z`).getUTCDay();
      if (ds === 6 || ds === 0 || (ds === 5 && i === 0)) dias.push(d);
      if (ds === 0) break;
    }
    return dias;
  }, [ahora]);
  const tipos = useMemo(() => [...new Set(eventos.map(e => e.tipo))].sort(), [eventos]);
  // Día que se muestra en cada evento según el filtro elegido
  const diaDe = (e: Evento) => filtro === "hoy" ? hoy : filtro === "manana" ? manana
    : filtro === "finde" ? finde.find(d => ocurreEl(e, d)) ?? e.desde : e.desde < hoy ? hoy : e.desde;
  const lista = useMemo(() => eventos.filter(e =>
    (!familia || e.familia) && (!tipo || e.tipo === tipo) &&
    (filtro === "todo" || (filtro === "hoy" && ocurreEl(e, hoy)) || (filtro === "manana" && ocurreEl(e, manana))
      || (filtro === "finde" && finde.some(d => ocurreEl(e, d)))))
    // primero los de un solo día (conciertos, teatro…) y después las exposiciones de varios días
    .sort((a, b) => Number(a.desde !== a.hasta) - Number(b.desde !== b.hasta)), [eventos, filtro, tipo, familia, hoy, manana, finde]);
  const chip = (activo: boolean) => ({ paddingHorizontal: 14, height: 36, justifyContent: "center" as const, borderRadius: 99, backgroundColor: activo ? c.texto : c.tarjeta });
  const textoChip = (activo: boolean) => ({ color: activo ? c.fondo : c.texto, fontWeight: "700" as const });
  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={cerrar}>
      <View style={{ flex: 1, backgroundColor: c.fondo, padding: 16, paddingBottom: ins.bottom, gap: 10 }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <Text style={{ color: c.texto, fontSize: 24, fontWeight: "800" }}>Agenda de Vitoria</Text>
          <Pressable onPress={cerrar}><Text style={{ color: c.acento, fontSize: 17 }}>Cerrar</Text></Pressable>
        </View>
        {nFamilia > 0 && (
          <Pressable onPress={() => setFamilia(!familia)}
            style={{ flexDirection: "row", alignItems: "center", gap: 10, padding: 12, borderRadius: 14,
              backgroundColor: familia ? c.ok : alfa(c.ok, 0.12) }}>
            <Icono n="ninos" color={familia ? "#fff" : c.ok} tam={20} />
            <View style={{ flex: 1 }}>
              <Text style={{ color: familia ? "#fff" : c.texto, fontSize: 16, fontWeight: "800" }}>Niños y familia</Text>
              <Text style={{ color: familia ? "#ffffffcc" : c.suave, fontSize: 13 }}>
                {familia ? "Solo planes para ir con niños · toca para ver todo" : `${nFamilia} planes: cuentacuentos, teatro, talleres…`}
              </Text>
            </View>
            <View style={{ width: 24, height: 24, borderRadius: 12, alignItems: "center", justifyContent: "center",
              backgroundColor: familia ? "#fff" : "transparent", borderWidth: familia ? 0 : 2, borderColor: c.ok }}>
              {familia && <Text style={{ color: c.ok, fontWeight: "900" }}>✓</Text>}
            </View>
          </Pressable>
        )}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }} style={{ flexGrow: 0, flexShrink: 0, height: 40 }}>
          {([["todo", "Todo"], ["hoy", "Hoy"], ["manana", "Mañana"], ["finde", "Fin de semana"]] as const).map(([f, t]) => (
            <Pressable key={f} onPress={() => setFiltro(f)} style={chip(filtro === f)}><Text style={textoChip(filtro === f)}>{t}</Text></Pressable>
          ))}
        </ScrollView>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }} style={{ flexGrow: 0, flexShrink: 0, height: 40 }}>
          <Pressable onPress={() => setTipo(null)} style={chip(!tipo)}><Text style={textoChip(!tipo)}>Todos</Text></Pressable>
          {tipos.map(t => (
            <Pressable key={t} onPress={() => setTipo(tipo === t ? null : t)} style={chip(tipo === t)}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                <Icono n={icono(t)} color={tipo === t ? c.fondo : c.texto} tam={13} />
                <Text style={textoChip(tipo === t)}>{t}</Text>
              </View>
            </Pressable>
          ))}
        </ScrollView>
        <FlatList data={lista} keyExtractor={e => e.id}
          ListEmptyComponent={<Etiqueta>{familia ? "No hay planes para niños con esos filtros. Prueba con «Todo»." : "No hay eventos con esos filtros."}</Etiqueta>}
          renderItem={({ item: e }) => <FilaEvento e={e} dia={etiquetaDia(diaDe(e), hoy, manana)} />} />
        <Etiqueta>{familia
          ? "Planes para niños: los que la agenda marca como infantiles o familiares, o que indican edades de niños. Toca uno para ver información o entradas."
          : "Fuente: agenda cultural de Euskadi (Open Data Euskadi). Toca un evento para ver información o entradas."}</Etiqueta>
      </View>
    </Modal>
  );
}

export function TarjetaAgenda({ eventos }: { eventos: Evento[] }) {
  const c = useColores();
  const [abierta, setAbierta] = useState<null | "todo" | "familia">(null);
  if (!eventos.length) return null;
  const ahora = Date.now();
  const hoy = fechaMadrid(ahora), manana = fechaMadrid(ahora + 86400e3);
  const deHoy = eventos.filter(e => ocurreEl(e, hoy) && e.desde === e.hasta);
  const proximos = (deHoy.length ? deHoy : eventos.filter(e => e.desde === e.hasta)).slice(0, 3);
  const familia = eventos.filter(e => e.familia);
  const semana = fechaMadrid(ahora + 7 * 86400e3);
  const familiaSemana = familia.filter(e => e.desde <= semana && e.desde === e.hasta);
  return (
    <Tarjeta>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8, flexShrink: 1 }}>
          <Icono n="teatro" color={c.acento} tam={17} />
          <Text style={{ color: c.texto, fontSize: 17, fontWeight: "700" }}>{deHoy.length ? `Hoy en la agenda · ${deHoy.length}` : "Próximamente"}</Text>
        </View>
        <Pressable onPress={() => setAbierta("todo")}><Text style={{ color: c.acento, fontSize: 15 }}>Ver todo ({eventos.length})</Text></Pressable>
      </View>
      {proximos.map(e => <FilaEvento key={e.id} e={e} dia={etiquetaDia(e.desde < hoy ? hoy : e.desde, hoy, manana)} />)}
      {familia.length > 0 && (
        <Pressable onPress={() => setAbierta("familia")}
          style={({ pressed }) => ({ flexDirection: "row", alignItems: "center", gap: 10, padding: 12, borderRadius: 14,
            backgroundColor: alfa(c.ok, 0.12), opacity: pressed ? 0.7 : 1 })}>
          <Icono n="ninos" color={c.ok} tam={20} />
          <View style={{ flex: 1 }}>
            <Text style={{ color: c.texto, fontSize: 15, fontWeight: "800" }}>Con niños</Text>
            <Text numberOfLines={1} style={{ color: c.suave, fontSize: 13 }}>
              {familiaSemana.length ? `${familiaSemana.length} planes esta semana · ${familiaSemana[0].nombre}` : `${familia.length} planes próximamente`}
            </Text>
          </View>
          <Icono n="flecha" color={c.ok} tam={14} />
        </Pressable>
      )}
      <AgendaCompleta eventos={eventos} visible={abierta != null} familiaAlAbrir={abierta === "familia"} cerrar={() => setAbierta(null)} />
    </Tarjeta>
  );
}
