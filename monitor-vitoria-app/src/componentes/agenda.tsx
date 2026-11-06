/** Agenda cultural de Vitoria: tarjeta en Inicio y lista completa con filtros. */
import { useMemo, useState } from "react";
import { ActionSheetIOS, Alert, FlatList, Image, Linking, Modal, Platform, Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { fechaMadrid } from "../lib/formato";
import { ocurreEl, type Evento } from "../lib/fuentes/agenda";
import { useColores } from "../lib/tema";
import { Etiqueta, Tarjeta } from "./ui";

const ICONO: Record<string, string> = {
  Concierto: "🎵", Teatro: "🎭", Danza: "💃", Exposición: "🖼️", Cine: "🎬", Festival: "🎪", Conferencia: "🎤",
  Formación: "📚", Fiestas: "🎉", Infantil: "🧸", Bertsolarismo: "🗣️", Deportes: "⚽",
};
const icono = (tipo: string) => ICONO[tipo] ?? "📅";

const DIAS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
function etiquetaDia(d: string, hoy: string, manana: string): string {
  if (d === hoy) return "Hoy";
  if (d === manana) return "Mañana";
  const f = new Date(`${d}T12:00:00Z`);
  return `${DIAS[f.getUTCDay()]} ${f.getUTCDate()}`;
}

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
          <Text style={{ fontSize: 26 }}>{icono(e.tipo)}</Text>
        </View>
      )}
      <View style={{ flex: 1, gap: 2 }}>
        <Text numberOfLines={2} style={{ color: c.texto, fontSize: 15, fontWeight: "700" }}>{e.nombre}</Text>
        <Text numberOfLines={1} style={{ color: c.suave, fontSize: 13 }}>
          {icono(e.tipo)} {e.tipo}{e.lugar ? ` · ${e.lugar}` : ""}
        </Text>
        <Text numberOfLines={1} style={{ color: c.acento, fontSize: 13, fontWeight: "600" }}>
          {dia}{e.hora ? ` · ${e.hora}` : ""}{e.desde !== e.hasta ? " · varios días" : ""}{e.precio ? ` · ${e.precio}` : ""}
        </Text>
      </View>
    </Pressable>
  );
}

type Filtro = "hoy" | "manana" | "finde" | "todo";

function AgendaCompleta({ eventos, visible, cerrar }: { eventos: Evento[]; visible: boolean; cerrar: () => void }) {
  const c = useColores();
  const ins = useSafeAreaInsets();
  const [filtro, setFiltro] = useState<Filtro>("todo");
  const [tipo, setTipo] = useState<string | null>(null);
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
  const lista = useMemo(() => eventos.filter(e =>
    (!tipo || e.tipo === tipo) &&
    (filtro === "todo" || (filtro === "hoy" && ocurreEl(e, hoy)) || (filtro === "manana" && ocurreEl(e, manana))
      || (filtro === "finde" && finde.some(d => ocurreEl(e, d))))), [eventos, filtro, tipo, hoy, manana, finde]);
  const chip = (activo: boolean) => ({ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 99, backgroundColor: activo ? c.texto : c.tarjeta });
  const textoChip = (activo: boolean) => ({ color: activo ? c.fondo : c.texto, fontWeight: "700" as const });
  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={cerrar}>
      <View style={{ flex: 1, backgroundColor: c.fondo, padding: 16, paddingBottom: ins.bottom, gap: 10 }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <Text style={{ color: c.texto, fontSize: 24, fontWeight: "800" }}>Agenda de Vitoria</Text>
          <Pressable onPress={cerrar}><Text style={{ color: c.acento, fontSize: 17 }}>Cerrar</Text></Pressable>
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }} style={{ flexGrow: 0 }}>
          {([["todo", "Todo"], ["hoy", "Hoy"], ["manana", "Mañana"], ["finde", "Fin de semana"]] as const).map(([f, t]) => (
            <Pressable key={f} onPress={() => setFiltro(f)} style={chip(filtro === f)}><Text style={textoChip(filtro === f)}>{t}</Text></Pressable>
          ))}
        </ScrollView>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }} style={{ flexGrow: 0 }}>
          <Pressable onPress={() => setTipo(null)} style={chip(!tipo)}><Text style={textoChip(!tipo)}>Todos</Text></Pressable>
          {tipos.map(t => (
            <Pressable key={t} onPress={() => setTipo(tipo === t ? null : t)} style={chip(tipo === t)}>
              <Text style={textoChip(tipo === t)}>{icono(t)} {t}</Text>
            </Pressable>
          ))}
        </ScrollView>
        <FlatList data={lista} keyExtractor={e => e.id}
          ListEmptyComponent={<Etiqueta>No hay eventos con esos filtros.</Etiqueta>}
          renderItem={({ item: e }) => <FilaEvento e={e} dia={etiquetaDia(e.desde < hoy ? hoy : e.desde, hoy, manana)} />} />
        <Etiqueta>Fuente: agenda cultural de Euskadi (Open Data Euskadi). Toca un evento para ver información o entradas.</Etiqueta>
      </View>
    </Modal>
  );
}

export function TarjetaAgenda({ eventos }: { eventos: Evento[] }) {
  const c = useColores();
  const [abierta, setAbierta] = useState(false);
  if (!eventos.length) return null;
  const ahora = Date.now();
  const hoy = fechaMadrid(ahora), manana = fechaMadrid(ahora + 86400e3);
  const deHoy = eventos.filter(e => ocurreEl(e, hoy) && e.desde === e.hasta);
  const proximos = (deHoy.length ? deHoy : eventos.filter(e => e.desde === e.hasta)).slice(0, 3);
  return (
    <Tarjeta>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
        <Text style={{ color: c.texto, fontSize: 17, fontWeight: "700" }}>{deHoy.length ? `Hoy en la agenda · ${deHoy.length}` : "Próximamente"}</Text>
        <Pressable onPress={() => setAbierta(true)}><Text style={{ color: c.acento, fontSize: 15 }}>Ver todo ({eventos.length})</Text></Pressable>
      </View>
      {proximos.map(e => <FilaEvento key={e.id} e={e} dia={etiquetaDia(e.desde < hoy ? hoy : e.desde, hoy, manana)} />)}
      <AgendaCompleta eventos={eventos} visible={abierta} cerrar={() => setAbierta(false)} />
    </Tarjeta>
  );
}
