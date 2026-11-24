"""Dibujador de perfiles según consigna de calidad.

App de escritorio para Windows. Funciona 100 % sin conexión: no envía
ningún dato a la red. Lee la consigna desde Excel (.xlsx) o CSV, dibuja el
perfil con sus cotas y tolerancias, y marca en verde/rojo las medidas OK/NOK.
"""
from __future__ import annotations

import os
import shutil
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import matplotlib

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from perfil_app import analisis, core, neumatico  # noqa: E402

APP_NOMBRE = "Dibujador de Perfiles"


def recurso(rel: str) -> str:
    """Ruta a un recurso, tanto en desarrollo como dentro del .exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NOMBRE)
        self.geometry("1280x800")
        self.minsize(900, 600)

        self.ruta: str | None = None
        self.consigna: core.Consigna | None = None
        self.var_puntos = tk.BooleanVar(value=True)
        self.var_cotas = tk.BooleanVar(value=True)
        self.var_seccion = tk.StringVar(value=neumatico.CARCASA)
        self.var_vista = tk.StringVar(value="Plano (semisección)")
        aj = neumatico.Ajustes()
        self.var_chaflan = tk.DoubleVar(value=aj.chaflan)
        self.var_rigidez = tk.DoubleVar(value=aj.rigidez)
        self.var_rigidez_fe = tk.DoubleVar(value=aj.rigidez_por_producto.get("FE", aj.rigidez))
        self.var_ruletaje = tk.BooleanVar(value=False)
        self.var_base_bt = tk.DoubleVar(value=neumatico.Ajustes().base_bt)
        self.var_rampa_bt = tk.DoubleVar(value=neumatico.Ajustes().rampa_bt)
        self.var_tecnico = tk.BooleanVar(value=False)
        self.vars_desp: dict[str, tk.DoubleVar] = {}

        self._construir_ui()
        self.bind("<Control-o>", lambda e: self.abrir())
        self.bind("<F5>", lambda e: self.recargar())

        if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
            self.cargar(sys.argv[1])

    # ------------------------------------------------------------------ UI
    def _construir_ui(self):
        barra = self.barra = ttk.Frame(self, padding=(6, 6))
        barra.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(barra, text="📂 Abrir consigna…", command=self.abrir).pack(side=tk.LEFT)
        ttk.Button(barra, text="⟳ Recargar (F5)", command=self.recargar).pack(side=tk.LEFT, padx=4)
        ttk.Button(barra, text="💾 Exportar…", command=self.exportar).pack(side=tk.LEFT, padx=4)
        ttk.Separator(barra, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Checkbutton(barra, text="Nombres de puntos", variable=self.var_puntos,
                        command=self.redibujar).pack(side=tk.LEFT)
        ttk.Checkbutton(barra, text="Cotas", variable=self.var_cotas,
                        command=self.redibujar).pack(side=tk.LEFT, padx=6)
        # Opciones para consignas de neumático
        self.barra_neum = ttk.Frame(barra)
        ttk.Label(self.barra_neum, text="Sección:").pack(side=tk.LEFT, padx=(8, 2))
        cb = ttk.Combobox(self.barra_neum, textvariable=self.var_seccion, state="readonly", width=9,
                          values=(neumatico.CARCASA, neumatico.BANDAJE, "Todo"))
        cb.pack(side=tk.LEFT)
        cb.bind("<<ComboboxSelected>>", lambda e: self._actualizar_neumatico())
        ttk.Label(self.barra_neum, text="Vista:").pack(side=tk.LEFT, padx=(8, 2))
        cb2 = ttk.Combobox(self.barra_neum, textvariable=self.var_vista, state="readonly", width=20,
                           values=("Plano (semisección)", "Plano con detalle de aire", "Posiciones (TRAZO)", "Sección apilada"))
        cb2.pack(side=tk.LEFT)
        cb2.bind("<<ComboboxSelected>>", lambda e: self.redibujar())
        # Segunda fila: parámetros del aire (solo neumático)
        self.barra_aire = ttk.Frame(self, padding=(6, 0, 6, 6))
        ttk.Label(self.barra_aire, text="Chaflán (× esp.):").pack(side=tk.LEFT)
        for var, de, a in ((self.var_chaflan, 1, 12), (self.var_rigidez, 0.5, 30), (self.var_rigidez_fe, 0.5, 40)):
            if var is self.var_rigidez:
                ttk.Label(self.barra_aire, text="Rigidez (× esp.):").pack(side=tk.LEFT, padx=(12, 0))
            elif var is self.var_rigidez_fe:
                ttk.Label(self.barra_aire, text="Rigidez FE:").pack(side=tk.LEFT, padx=(8, 0))
            sp = ttk.Spinbox(self.barra_aire, from_=de, to=a, increment=0.5, width=5, textvariable=var,
                             command=self._actualizar_neumatico)
            sp.pack(side=tk.LEFT, padx=(4, 0))
            sp.bind("<Return>", lambda e: self._actualizar_neumatico())
            sp.bind("<FocusOut>", lambda e: self._actualizar_neumatico())
        ttk.Checkbutton(self.barra_aire, text="Simular ruletaje (apliques)", variable=self.var_ruletaje,
                        command=self._actualizar_neumatico).pack(side=tk.LEFT, padx=(16, 0))
        for texto, var, de, a, inc in (("BT base (mm):", self.var_base_bt, 0.1, 4, 0.1),
                                       ("rampa falaise (mm):", self.var_rampa_bt, 1, 27, 0.5)):
            ttk.Label(self.barra_aire, text=texto).pack(side=tk.LEFT, padx=(12, 0))
            sp = ttk.Spinbox(self.barra_aire, from_=de, to=a, increment=inc, width=4, textvariable=var,
                             command=self._actualizar_neumatico)
            sp.pack(side=tk.LEFT, padx=(2, 0))
            sp.bind("<Return>", lambda e: self._actualizar_neumatico())
        ttk.Button(self.barra_aire, text="⚙ Optimizar posiciones (±2 mm)…",
                   command=self.dialogo_optimizar).pack(side=tk.LEFT, padx=(16, 0))
        self.var_total_aire = tk.StringVar()
        ttk.Label(self.barra_aire, textvariable=self.var_total_aire, foreground="#b00000",
                  font=("TkDefaultFont", 10, "bold")).pack(side=tk.LEFT, padx=(16, 0))
        ttk.Button(barra, text="Guardar plantilla de ejemplo…",
                   command=self.guardar_plantilla).pack(side=tk.RIGHT)
        self.boton_tecnico = ttk.Button(barra, text="🔧 Modo técnico", command=self._alternar_tecnico)
        ttk.Button(barra, text="? Ayuda", command=self.ayuda).pack(side=tk.RIGHT, padx=4)

        self.estado = tk.StringVar(value="Abre una consigna (.xlsx o .csv) para empezar.  "
                                         "Todo se procesa en este equipo, sin conexión.")
        ttk.Label(self, textvariable=self.estado, anchor=tk.W, padding=(6, 3),
                  relief=tk.SUNKEN).pack(side=tk.BOTTOM, fill=tk.X)

        panel = self.paned = ttk.PanedWindow(self, orient=tk.VERTICAL)
        panel.pack(fill=tk.BOTH, expand=True)

        # Zona principal: dibujo + panel de resumen (vista simple)
        principal = ttk.Frame(panel)
        self.panel_simple = ttk.Frame(principal, padding=(8, 4), width=360)
        marco_dibujo = ttk.Frame(principal)
        marco_dibujo.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.fig = Figure(figsize=(8, 6), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=marco_dibujo)
        NavigationToolbar2Tk(self.canvas, marco_dibujo).update()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        panel.add(principal, weight=4)
        self._construir_panel_simple()

        # Tablas: cotas/productos y bolsas de aire
        self.pestanas = ttk.Notebook(panel)
        marco_tabla = ttk.Frame(self.pestanas)
        self.pestanas.add(marco_tabla, text="Cotas / Productos")
        marco_aire = self.marco_aire = ttk.Frame(self.pestanas)
        self.pestanas.add(marco_aire, text="Aire entre productos")
        self.tabla_aire = ttk.Treeview(marco_aire, show="headings", height=7)
        self.tabla_aire.configure(columns=[c for c, _, _ in TABLA_AIRE])
        for c, t, a in TABLA_AIRE:
            self.tabla_aire.heading(c, text=t)
            self.tabla_aire.column(c, width=a, anchor=tk.CENTER)
        self.tabla_aire.tag_configure("GRANDE", foreground="#b00000")
        self.tabla_aire.tag_configure("ARO", foreground="#888888")
        sba = ttk.Scrollbar(marco_aire, orient=tk.VERTICAL, command=self.tabla_aire.yview)
        self.tabla_aire.configure(yscrollcommand=sba.set)
        self.tabla_aire.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sba.pack(side=tk.RIGHT, fill=tk.Y)
        marco_an = self.marco_analisis = ttk.Frame(self.pestanas)
        self.pestanas.add(marco_an, text="Análisis y ruletaje")
        barra_an = ttk.Frame(marco_an)
        barra_an.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(barra_an, text="💾 Guardar informe…", command=self.guardar_informe).pack(side=tk.LEFT, pady=2)
        ttk.Button(barra_an, text="⚙ Calcular plan de ruletaje (ruletas 20 mm + multiperfil FE)",
                   command=self.calcular_plan).pack(side=tk.LEFT, padx=8, pady=2)
        ttk.Label(barra_an, text="Ver en el dibujo:").pack(side=tk.LEFT)
        self.var_plan = tk.StringVar(value="Sin ruletaje")
        self.cb_plan = ttk.Combobox(barra_an, textvariable=self.var_plan, state="readonly", width=34,
                                    values=("Sin ruletaje",))
        self.cb_plan.pack(side=tk.LEFT, padx=4)
        self.cb_plan.bind("<<ComboboxSelected>>", lambda e: self._actualizar_neumatico())
        self.planes = []
        self.texto_analisis = tk.Text(marco_an, wrap=tk.WORD, height=8, font=("TkFixedFont", 9))
        sbt = ttk.Scrollbar(marco_an, orient=tk.VERTICAL, command=self.texto_analisis.yview)
        self.texto_analisis.configure(yscrollcommand=sbt.set)
        self.texto_analisis.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sbt.pack(side=tk.RIGHT, fill=tk.Y)
        self.tabla = ttk.Treeview(marco_tabla, show="headings", height=7)
        self._columnas_tabla(TABLA_COTAS)
        self.tabla.tag_configure("OK", foreground=core.COLOR_OK)
        self.tabla.tag_configure("NOK", foreground=core.COLOR_NOK)
        self.tabla.tag_configure("AVISO", foreground=core.COLOR_AVISO)
        sb = ttk.Scrollbar(marco_tabla, orient=tk.VERTICAL, command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=sb.set)
        self.tabla.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        panel.add(self.pestanas, weight=1)

        self._pantalla_inicio()

    # ------------------------------------------------------ vista simple
    def _construir_panel_simple(self):
        p = self.panel_simple
        p.pack_propagate(False)
        titulo = ("TkDefaultFont", 10, "bold")
        ttk.Label(p, text="AIRE ENTRE PRODUCTOS", font=titulo).pack(anchor=tk.W)
        ttk.Label(p, text="PS · BJ · PTR · FE  (sin la zona del aro)", foreground="#666").pack(anchor=tk.W)
        self.lbl_aire = tk.Label(p, text="—", font=("TkDefaultFont", 26, "bold"), fg="#b00000", anchor=tk.W)
        self.lbl_aire.pack(anchor=tk.W, fill=tk.X)
        self.lbl_aire_sub = ttk.Label(p, text="", foreground="#444")
        self.lbl_aire_sub.pack(anchor=tk.W)

        ttk.Separator(p).pack(fill=tk.X, pady=6)
        ttk.Label(p, text="ZONAS CON AIRE", font=titulo).pack(anchor=tk.W)
        self.marco_zonas = ttk.Frame(p)
        self.marco_zonas.pack(anchor=tk.W, fill=tk.X)

        ttk.Separator(p).pack(fill=tk.X, pady=6)
        ttk.Label(p, text="RFID", font=titulo).pack(anchor=tk.W)
        fila = ttk.Frame(p)
        fila.pack(anchor=tk.W, fill=tk.X)
        self.var_rfid = tk.BooleanVar(value=False)
        self.var_rfid_pos = tk.DoubleVar(value=0.0)
        ttk.Checkbutton(fila, text="Ver RFID, en (mm):", variable=self.var_rfid,
                        command=self._actualizar_neumatico).pack(side=tk.LEFT)
        sp = ttk.Spinbox(fila, from_=0, to=300, increment=1, width=6, textvariable=self.var_rfid_pos,
                         command=self._mover_rfid)
        sp.pack(side=tk.LEFT, padx=4)
        sp.bind("<Return>", lambda e: self._mover_rfid())
        self.lbl_rfid = tk.Label(p, text="", justify=tk.LEFT, anchor=tk.W, wraplength=330)
        self.lbl_rfid.pack(anchor=tk.W, fill=tk.X)

        ttk.Separator(p).pack(fill=tk.X, pady=6)
        ttk.Label(p, text="POSICIÓN DE LOS PRODUCTOS", font=titulo).pack(anchor=tk.W)
        ttk.Label(p, text="Mover (mm, + hacia fuera) y ver cómo cambia el aire", foreground="#666").pack(anchor=tk.W)
        self.marco_prods = ttk.Frame(p)
        self.marco_prods.pack(anchor=tk.W, fill=tk.X, pady=(2, 4))
        botones = ttk.Frame(p)
        botones.pack(anchor=tk.W, fill=tk.X)
        ttk.Button(botones, text="🔍 Buscar mejor posición (±2 mm)", command=self._buscar_mejor).pack(side=tk.LEFT)
        ttk.Button(botones, text="↺ Consigna", command=self._volver_consigna).pack(side=tk.LEFT, padx=4)

    def _rellenar_productos_simple(self):
        for w in self.marco_prods.winfo_children():
            w.destroy()
        self.vars_desp = {}
        cons = self.consigna
        f = neumatico._f
        ttk.Label(self.marco_prods, text="Prod.", foreground="#666").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(self.marco_prods, text="Consigna", foreground="#666").grid(row=0, column=1, sticky=tk.W, padx=4)
        ttk.Label(self.marco_prods, text="Mover", foreground="#666").grid(row=0, column=2, sticky=tk.W)
        ttk.Label(self.marco_prods, text="Queda", foreground="#666").grid(row=0, column=3, sticky=tk.W, padx=4)
        fila = 1
        for p in cons.de(neumatico.CARCASA):
            if not p.movible:
                continue
            var = tk.DoubleVar(value=p.desplazamiento)
            self.vars_desp[p.codigo] = var
            ttk.Label(self.marco_prods, text=p.codigo, font=("TkDefaultFont", 9, "bold")).grid(row=fila, column=0,
                                                                                               sticky=tk.W)
            ttk.Label(self.marco_prods, text=f"{p.trazo_tipo} {f(p.trazo)}").grid(row=fila, column=1, sticky=tk.W,
                                                                               padx=4)
            sp = ttk.Spinbox(self.marco_prods, from_=-10, to=10, increment=0.5, width=5, textvariable=var,
                             command=self._aplicar_movimientos)
            sp.grid(row=fila, column=2, sticky=tk.W)
            sp.bind("<Return>", lambda e: self._aplicar_movimientos())
            lbl = ttk.Label(self.marco_prods, text="")
            lbl.grid(row=fila, column=3, sticky=tk.W, padx=4)
            var._etiqueta = lbl  # noqa: SLF001 - etiqueta con la posición resultante
            fila += 1

    def _aplicar_movimientos(self):
        cons = self.consigna
        desp = {}
        for cod, var in self.vars_desp.items():
            try:
                v = float(var.get())
            except (tk.TclError, ValueError):
                v = 0.0
            if v:
                desp[cod] = v
        neumatico.aplicar_desplazamientos(cons, desp)
        self._actualizar_neumatico()

    def _buscar_mejor(self):
        if not isinstance(self.consigna, neumatico.ConsignaNeumatico):
            return
        self.estado.set("Buscando la mejor posición de los productos (±2 mm)…")
        self.config(cursor="watch")
        self.update()
        try:
            aj = self.ajustes()
            aj.mostrar_rfid, aj.ruletas, aj.multiperfil = False, (), False
            r = neumatico.optimizar(self.consigna, neumatico.CARCASA, aj, 2.0, 0.5,
                                    [c for c in self.vars_desp])
        finally:
            self.config(cursor="")
        for cod, var in self.vars_desp.items():
            var.set(r.desplazamientos.get(cod, 0.0))
        self._aplicar_movimientos()
        messagebox.showinfo("Mejor posición",
                            f"Aire entre productos: {neumatico._f(round(r.aire_antes, 1))} → "
                            f"{neumatico._f(round(r.aire_despues, 1))} mm²\n\n"
                            + ("\n".join(f"{k}: {v:+g} mm" for k, v in r.desplazamientos.items())
                               or "La consigna ya es la mejor posición (±2 mm)."))

    def _volver_consigna(self):
        for var in self.vars_desp.values():
            var.set(0.0)
        self._aplicar_movimientos()

    def _refrescar_panel(self, total, zonas, rfid_info):
        f = neumatico._f
        color = "#1a7f37" if total < 3 else ("#d97706" if total < 8 else "#b00000")
        self.lbl_aire.configure(text=f"{f(round(total, 1))} mm²", fg=color)
        estado = "BIEN" if total < 3 else ("ATENCIÓN" if total < 8 else "ALTO")
        self.lbl_aire_sub.configure(text=f"{estado} · en la sección, por lado")
        for w in self.marco_zonas.winfo_children():
            w.destroy()
        colores = {"ALTO": "#b00000", "MEDIO": "#d97706", "BAJO": "#9a7d00"}
        if not zonas:
            ttk.Label(self.marco_zonas, text="Sin zonas de aire apreciable.").pack(anchor=tk.W)
        for z in zonas[:6]:
            pares = ", ".join(z.pares)
            tk.Label(self.marco_zonas, text=f"● {z.nombre}  {f(round(z.xc))} mm  ({f(round(z.x0))}–{f(round(z.x1))})",
                     fg=colores[z.riesgo], font=("TkDefaultFont", 9, "bold"), anchor=tk.W).pack(anchor=tk.W)
            ttk.Label(self.marco_zonas, text=f"     {pares} · {f(round(z.area, 1))} mm²", foreground="#444"
                      ).pack(anchor=tk.W)
        # RFID
        if rfid_info is None:
            self.lbl_rfid.configure(text="La consigna no tiene RFID.", fg="#666")
        else:
            bj = rfid_info.get("bj")
            rango = f"{f(round(rfid_info['x0']))}–{f(round(rfid_info['x1']))} mm"
            if bj and bj["cubre_todo"]:
                txt = (f"✔ PROTEGIDO por el BJ ({rango})\nMargen a los bordes del BJ: {f(round(bj['margen_int']))} y "
                       f"{f(round(bj['margen_ext']))} mm · BJ encima {f(round(bj['espesor_min'], 1))}–"
                       f"{f(round(bj['espesor_max'], 1))} mm")
                col = "#1a7f37" if min(bj["margen_int"], bj["margen_ext"]) >= 5 else "#d97706"
            else:
                pct = f" (cubre el {bj['cubierto_pct']:.0f} %)" if bj else ""
                txt = f"✖ NO protegido del todo por el BJ{pct} ({rango})"
                col = "#b00000"
            self.lbl_rfid.configure(text=txt, fg=col)
        # posición resultante de cada producto
        cons = self.consigna
        for p in cons.productos:
            var = self.vars_desp.get(p.codigo)
            if var is not None and abs(float(var.get() or 0) - p.desplazamiento) > 1e-9:
                var.set(p.desplazamiento)   # p. ej. si se aplicó una propuesta desde el modo técnico
            if var is not None and hasattr(var, "_etiqueta"):
                txt = f"{p.trazo_tipo} {f(round((p.trazo or 0) + p.desplazamiento, 1))}"
                var._etiqueta.configure(text=txt, foreground="#b00000" if p.desplazamiento else "#444")

    def _alternar_tecnico(self):
        self.var_tecnico.set(not self.var_tecnico.get())
        self._aplicar_modo()

    def _aplicar_modo(self):
        es_neum = isinstance(self.consigna, neumatico.ConsignaNeumatico)
        tecnico = self.var_tecnico.get() or not es_neum
        self.boton_tecnico.configure(text="◀ Vista simple" if self.var_tecnico.get() else "🔧 Modo técnico")
        if es_neum:
            self.boton_tecnico.pack(side=tk.RIGHT, padx=4)
            self.panel_simple.pack(side=tk.RIGHT, fill=tk.Y, before=self.canvas.get_tk_widget().master)
        else:
            self.boton_tecnico.pack_forget()
            self.panel_simple.pack_forget()
        if es_neum and tecnico:
            self.barra_neum.pack(side=tk.LEFT)
            self.barra_aire.pack(side=tk.TOP, fill=tk.X, after=self.barra)
        else:
            self.barra_neum.pack_forget()
            self.barra_aire.pack_forget()
        presentes = self.paned.panes()
        if tecnico and str(self.pestanas) not in [str(x) for x in presentes]:
            self.paned.add(self.pestanas, weight=1)
        elif not tecnico and str(self.pestanas) in [str(x) for x in presentes]:
            self.paned.forget(self.pestanas)

    def _columnas_tabla(self, defin):
        cols = [c for c, _, _ in defin]
        self.tabla.configure(columns=cols)
        for c, t, a in defin:
            self.tabla.heading(c, text=t)
            self.tabla.column(c, width=a, anchor=tk.W if c in ("nombre", "puntos", "apel") else tk.CENTER)

    def _pantalla_inicio(self):
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        ax.axis("off")
        ax.text(0.5, 0.55, APP_NOMBRE, ha="center", fontsize=20, color=core.COLOR_PERFIL)
        ax.text(0.5, 0.45, "Pulsa «Abrir consigna…» (Ctrl+O): Excel de perfil o consigna de neumático", ha="center", fontsize=11, color="#666")
        self.canvas.draw()

    # ------------------------------------------------------------ acciones
    def abrir(self):
        ruta = filedialog.askopenfilename(
            title="Abrir consigna de calidad",
            filetypes=[("Consignas", "*.xlsx *.xlsm *.xls *.csv"), ("Excel", "*.xlsx *.xlsm *.xls"),
                       ("CSV", "*.csv"), ("Todos", "*.*")],
        )
        if ruta:
            self.cargar(ruta)

    def recargar(self):
        if self.ruta:
            self.cargar(self.ruta)

    def cargar(self, ruta: str):
        try:
            if neumatico.es_consigna_neumatico(ruta):
                return self._cargar_neumatico(ruta)
            consigna = core.cargar(ruta)
        except core.ErrorConsigna as e:
            messagebox.showerror("Error en la consigna", str(e))
            return
        except PermissionError:
            messagebox.showerror("No se puede leer",
                                 "El archivo está abierto en otro programa (¿Excel?). Ciérralo y recarga.")
            return
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Error al abrir", f"{type(e).__name__}: {e}")
            return
        self.ruta, self.consigna = ruta, consigna
        self._aplicar_modo()
        self.pestanas.hide(1)
        self.pestanas.hide(2)
        self._columnas_tabla(TABLA_COTAS)
        self.title(f"{APP_NOMBRE} — {os.path.basename(ruta)}")
        self.redibujar()
        self._rellenar_tabla()
        nok = sum(1 for c in consigna.cotas if c.estado == "NOK")
        ok = sum(1 for c in consigna.cotas if c.estado == "OK")
        msg = f"{os.path.basename(ruta)}: {len(consigna.cotas)} cotas"
        if ok or nok:
            msg += f"  ·  {ok} OK  ·  {nok} NOK"
        if consigna.avisos:
            msg += f"  ·  ⚠ {len(consigna.avisos)} aviso(s)"
            messagebox.showwarning("Avisos", "\n\n".join(consigna.avisos))
        self.estado.set(msg)

    def _cargar_neumatico(self, ruta: str):
        try:
            cons = neumatico.cargar(ruta)
        except PermissionError:
            messagebox.showerror("No se puede leer",
                                 "El archivo está abierto en otro programa (¿Excel?). Ciérralo y recarga.")
            return
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Error al abrir", f"{type(e).__name__}: {e}")
            return
        self.ruta, self.consigna = ruta, cons
        self.planes = []
        self.var_plan.set("Sin ruletaje")
        self.cb_plan["values"] = ("Sin ruletaje",)
        rf = [p for p in cons.productos if p.es_rfid and p.tramo_rfid]
        if rf:
            self.var_rfid_pos.set(round(rf[0].tramo_rfid[0], 1))
        self.title(f"{APP_NOMBRE} — {os.path.basename(ruta)}")
        self.var_seccion.set(neumatico.CARCASA)
        self._aplicar_modo()
        self._rellenar_productos_simple()
        self.pestanas.add(self.marco_aire)
        self.pestanas.add(self.marco_analisis)
        self._columnas_tabla(TABLA_NEUMATICO)
        self._actualizar_neumatico()
        if cons.avisos:
            messagebox.showwarning("Avisos", "\n\n".join(cons.avisos))

    def _actualizar_neumatico(self):
        cons = self.consigna
        self.redibujar()
        self.tabla.delete(*self.tabla.get_children())
        f = neumatico._f
        prods = cons.de(self.var_seccion.get())
        for p in prods:
            self.tabla.insert("", tk.END, values=(
                p.codigo, p.apelacion, f(p.anchura), f(p.espesor), p.angulo, p.trazo_texto,
                "no se tiene en cuenta (RFID)" if p.es_rfid else
                (f(round(p.borde_int, 3)) if p.borde_int is not None else ""),
                f(round(p.borde_ext, 3)) if p.borde_ext is not None else "",
                p.longitud, f(p.peso)))
        info = [f"{k}: {v}" for k, v in cons.cabecera.items() if k in ("DIMENSIÓN", "CBL", "C.A.I.") and v]
        if cons.entre_tringles:
            info.append(f"Entre aros {f(cons.entre_tringles)}")
        # bolsas de aire
        self.tabla_aire.delete(*self.tabla_aire.get_children())
        aj_b = self.ajustes()
        aj_b.mostrar_rfid = False
        bolsas = neumatico.bolsas_de_aire(cons, self.var_seccion.get(), aj_b)
        esp = {p.codigo: p.espesor for p in cons.productos}
        for b in sorted(bolsas, key=lambda b: (b.zona_aro, -b.area)):
            tag = ("ARO",) if b.zona_aro else (("GRANDE",) if b.area >= 1 else ())
            self.tabla_aire.insert("", tk.END, tags=tag, values=(
                f"{b.abajo} ({f(esp.get(b.abajo))}) → {b.arriba} ({f(esp.get(b.arriba))})",
                f(round(b.x0, 1)), f(round(b.x1, 1)), f(round(b.area, 2)),
                f(round(b.alto, 2)), f(round(b.volumen_cm3, 2)), "aro (aprox.)" if b.zona_aro else ""))
        total = sum(b.area for b in bolsas if not b.zona_aro)
        vol = sum(b.volumen_cm3 for b in bolsas if not b.zona_aro)
        aro = sum(b.area for b in bolsas if b.zona_aro)
        txt = f"Aire: {f(round(total, 1))} mm² en sección · {f(round(vol, 1))} cm³ por lado"
        if aro:
            txt += f"   (+ {f(round(aro, 1))} mm² en zona aro, aprox.)"
        self.var_total_aire.set(txt + ("  · con ruletaje" if self.var_ruletaje.get() else ""))
        # análisis de aire y propuesta de ruletajes
        sec = self.var_seccion.get()
        sec = neumatico.CARCASA if sec == "Todo" else sec
        try:
            aj_sin = self.ajustes()
            aj_sin.ruletas, aj_sin.multiperfil, aj_sin.mostrar_rfid = (), False, False
            self.analisis = analisis.analizar(cons, sec, aj_sin)
            texto = self.analisis.texto(cons)
            rfid = neumatico.proteccion_rfid(cons, sec, aj_sin)
            if rfid:
                texto = "RFID (no cuenta para el aire)\n" + "\n".join(rfid) + "\n\n" + texto
            if getattr(self, "planes", None):
                texto = ("PLAN DE RULETAJE PROPUESTO (medios de máquina: ruletas de 20 mm y multiperfil del FE)\n"
                         + "\n".join(pl.texto() for pl in self.planes)
                         + "\n\nPara ensayar: empezar por el plan con menos aire; si no se puede montar todo, "
                           "las ruletas van en orden de importancia (la 1 es la que más aire quita).\n\n" + texto)
        except Exception as e:  # noqa: BLE001
            self.analisis, texto = None, f"No se pudo analizar: {type(e).__name__}: {e}"
        self.texto_analisis.configure(state=tk.NORMAL)
        self.texto_analisis.delete("1.0", tk.END)
        self.texto_analisis.insert("1.0", texto)
        self.texto_analisis.configure(state=tk.DISABLED)
        try:
            aj_r = self.ajustes()
            aj_r.mostrar_rfid = True
            prods_c = [p for p in cons.de(neumatico.CARCASA) if p.tramos]
            datos_rfid = neumatico._calcular_plano(cons, prods_c, aj_r)[4].get("rfid", [])
        except Exception:  # noqa: BLE001
            datos_rfid = []
        zonas = self.analisis.zonas if self.analisis else []
        self._refrescar_panel(self.analisis.total if self.analisis else total, zonas,
                              datos_rfid[0] if datos_rfid else None)
        desp = {p.codigo: p.desplazamiento for p in cons.productos if p.desplazamiento}
        if desp:
            info.insert(0, "PROPUESTA: " + ", ".join(f"{k} {v:+g} mm" for k, v in desp.items()))
        self.estado.set(f"{os.path.basename(self.ruta)}  ·  {len(prods)} productos  ·  " + "  ·  ".join(info))

    def guardar_informe(self):
        if not isinstance(self.consigna, neumatico.ConsignaNeumatico):
            return
        base = os.path.splitext(os.path.basename(self.ruta))[0]
        ruta = filedialog.asksaveasfilename(title="Guardar informe de aire y ruletajes",
                                            initialfile=f"{base}_analisis_aire.txt", defaultextension=".txt",
                                            filetypes=[("Texto", "*.txt")])
        if ruta:
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(self.texto_analisis.get("1.0", tk.END))
            self.estado.set(f"Informe guardado: {ruta}")

    def dialogo_optimizar(self):
        if not isinstance(self.consigna, neumatico.ConsignaNeumatico):
            return
        DialogoOptimizar(self)

    def ajustes(self) -> neumatico.Ajustes:
        def leer(var, defecto):
            try:
                return max(float(var.get()), 0.1)
            except (tk.TclError, ValueError):
                return defecto
        d = neumatico.Ajustes()
        aj = neumatico.Ajustes(chaflan=leer(self.var_chaflan, d.chaflan), rigidez=leer(self.var_rigidez, d.rigidez),
                               rigidez_por_producto={"FE": leer(self.var_rigidez_fe, d.rigidez_por_producto["FE"])},
                               ruletaje=self.var_ruletaje.get(),
                               base_bt=leer(self.var_base_bt, d.base_bt), rampa_bt=leer(self.var_rampa_bt, d.rampa_bt),
                               mostrar_rfid=self.var_rfid.get(), zoom_flanco=not self.var_tecnico.get())
        if getattr(self, "planes", None) and self.var_plan.get() != "Sin ruletaje":
            idx = list(self.cb_plan["values"]).index(self.var_plan.get()) - 1
            if 0 <= idx < len(self.planes):
                aj = self.planes[idx].ajustes(aj)
        return aj

    def _rfids(self):
        cons = self.consigna
        if not isinstance(cons, neumatico.ConsignaNeumatico):
            return []
        return [p for p in cons.productos if p.es_rfid and p.tramo_rfid]

    def _mover_rfid(self):
        """Coloca el borde interior del RFID en la cota indicada (para ver dónde queda y si lo protege el BJ)."""
        try:
            pos = float(self.var_rfid_pos.get())
        except (tk.TclError, ValueError):
            return
        for p in self._rfids():
            w = p.tramo_rfid[1] - p.tramo_rfid[0]
            p.tramo_rfid = (pos, pos + w)
        self.var_rfid.set(True)
        self._actualizar_neumatico()

    def calcular_plan(self):
        if not isinstance(self.consigna, neumatico.ConsignaNeumatico):
            return
        sec = self.var_seccion.get()
        sec = neumatico.CARCASA if sec == "Todo" else sec
        self.estado.set("Calculando el plan de ruletaje…")
        self.config(cursor="watch")
        self.update()
        try:
            base = self.ajustes()
            base.ruletas, base.multiperfil = (), False
            self.planes = analisis.planes_ruletaje(self.consigna, sec, base)
        finally:
            self.config(cursor="")
        nombres = ["Sin ruletaje", "Plan A: ruletas de 20 mm", "Plan B: multiperfil FE + ruletas 20 mm"]
        self.cb_plan["values"] = nombres
        self.var_plan.set(nombres[2] if self.planes[1].aire_final <= self.planes[0].aire_final else nombres[1])
        self._actualizar_neumatico()

    def redibujar(self):
        if not self.consigna:
            return
        if isinstance(self.consigna, neumatico.ConsignaNeumatico):
            v = self.var_vista.get()
            vista = ("detalle" if "detalle" in v else "plano" if v.startswith("Plano")
                     else "seccion" if v.startswith("Secc") else "posiciones")
            neumatico.dibujar(self.fig, self.consigna, self.var_seccion.get(), vista, self.var_cotas.get(),
                              self.ajustes())
            self.canvas.draw()
            return
        core.dibujar(self.fig, self.consigna, self.var_puntos.get(), self.var_cotas.get())
        self.canvas.draw()

    def _rellenar_tabla(self):
        self.tabla.delete(*self.tabla.get_children())
        f = core._fmt
        for c in self.consigna.cotas:
            if c.tol_sup == c.tol_inf:
                tol = f"±{f(c.tol_sup)}"
            else:
                tol = f"+{f(c.tol_sup)} / -{f(c.tol_inf)}"
            tag = c.estado or ("AVISO" if not c.coherente else "")
            self.tabla.insert("", tk.END, tags=(tag,), values=(
                c.nombre, c.tipo, f"{c.desde}→{c.hasta}" if c.hasta else c.desde,
                f(c.nominal), tol, f(c.minimo), f(c.maximo), f(c.valor_dibujo),
                "" if c.medido is None else f(c.medido), c.estado or ("⚠" if not c.coherente else ""),
            ))

    def exportar(self):
        if not self.consigna:
            messagebox.showinfo("Exportar", "Primero abre una consigna.")
            return
        base = os.path.splitext(os.path.basename(self.ruta))[0]
        ruta = filedialog.asksaveasfilename(
            title="Exportar dibujo", initialfile=base,
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf"), ("Imagen PNG", "*.png"), ("SVG", "*.svg"),
                       ("DXF (AutoCAD)", "*.dxf")],
        )
        if not ruta:
            return
        try:
            if ruta.lower().endswith(".dxf") and isinstance(self.consigna, neumatico.ConsignaNeumatico):
                raise ValueError("El DXF solo está disponible para perfiles; usa PDF, PNG o SVG.")
            if ruta.lower().endswith(".dxf"):
                core.exportar_dxf(self.consigna, ruta, con_cotas=self.var_cotas.get())
            else:
                self.fig.savefig(ruta, dpi=300)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Error al exportar", f"{type(e).__name__}: {e}")
            return
        self.estado.set(f"Exportado: {ruta}")

    def guardar_plantilla(self):
        ruta = filedialog.asksaveasfilename(
            title="Guardar plantilla de ejemplo", initialfile="consigna_ejemplo.xlsx",
            defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
        )
        if ruta:
            shutil.copyfile(recurso(os.path.join("ejemplos", "perfil_tubo.xlsx")), ruta)
            if messagebox.askyesno("Plantilla guardada", "Plantilla guardada. ¿Quieres abrirla en la app?"):
                self.cargar(ruta)

    def ayuda(self):
        messagebox.showinfo("Formato de la consigna", AYUDA)


TABLA_COTAS = (("nombre", "Cota", 180), ("tipo", "Tipo", 50), ("puntos", "Puntos", 90),
               ("nominal", "Nominal", 80), ("tol", "Tolerancia", 100), ("min", "Mín", 70), ("max", "Máx", 70),
               ("dibujo", "Perfil dibujado", 110), ("medido", "Medido", 80), ("estado", "Estado", 70))
class DialogoOptimizar(tk.Toplevel):
    """Busca cuánto mover cada producto (como mucho X mm) para dejar el mínimo aire."""

    def __init__(self, app: App):
        super().__init__(app)
        self.app = app
        self.title("Optimizar posiciones de los productos")
        self.transient(app)
        self.resizable(True, True)
        cons = app.consigna
        seccion = app.var_seccion.get()
        self.seccion = neumatico.CARCASA if seccion == "Todo" else seccion
        self.resultado = None

        f = ttk.Frame(self, padding=10)
        f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text=f"Sección: {self.seccion}.  Busca el desplazamiento de cada producto sobre su TRAZO "
                          "que deja menos aire en total\n(entre productos y en la zona del aro), con la rigidez y el "
                          "chaflán actuales. No cambia la consigna: es una propuesta.",
                  justify=tk.LEFT).pack(anchor=tk.W)
        fila = ttk.Frame(f)
        fila.pack(anchor=tk.W, pady=6)
        self.var_max = tk.DoubleVar(value=2.0)
        self.var_paso = tk.DoubleVar(value=0.5)
        ttk.Label(fila, text="Mover como mucho (mm):").pack(side=tk.LEFT)
        ttk.Spinbox(fila, from_=0.5, to=10, increment=0.5, width=5, textvariable=self.var_max).pack(side=tk.LEFT)
        ttk.Label(fila, text="  en pasos de (mm):").pack(side=tk.LEFT)
        ttk.Spinbox(fila, from_=0.1, to=2, increment=0.1, width=5, textvariable=self.var_paso).pack(side=tk.LEFT)

        ttk.Label(f, text="Productos que se pueden mover:").pack(anchor=tk.W)
        cajas = ttk.Frame(f)
        cajas.pack(anchor=tk.W)
        self.vars = {}
        for p in cons.de(self.seccion):
            if p.movible:
                v = tk.BooleanVar(value=True)
                self.vars[p.codigo] = v
                ttk.Checkbutton(cajas, text=f"{p.codigo} ({p.trazo_tipo} {neumatico._f(p.trazo)})",
                                variable=v).pack(side=tk.LEFT, padx=(0, 8))

        self.boton = ttk.Button(f, text="Calcular", command=self.calcular)
        self.boton.pack(anchor=tk.W, pady=6)
        self.barra = ttk.Progressbar(f, mode="determinate", maximum=1.0)
        self.barra.pack(fill=tk.X)
        self.var_res = tk.StringVar()
        ttk.Label(f, textvariable=self.var_res, foreground="#b00000",
                  font=("TkDefaultFont", 10, "bold")).pack(anchor=tk.W, pady=(8, 4))
        cols = (("prod", "Producto", 90), ("orig", "TRAZO consigna", 120), ("nuevo", "TRAZO propuesto", 130),
                ("delta", "Mover (mm)", 90), ("sentido", "Sentido", 140))
        self.tabla = ttk.Treeview(f, columns=[c for c, _, _ in cols], show="headings", height=8)
        for c, t, a in cols:
            self.tabla.heading(c, text=t)
            self.tabla.column(c, width=a, anchor=tk.CENTER)
        self.tabla.pack(fill=tk.BOTH, expand=True)
        bot = ttk.Frame(f)
        bot.pack(fill=tk.X, pady=(8, 0))
        self.b_ver = ttk.Button(bot, text="Ver propuesta en el dibujo", command=self.ver, state=tk.DISABLED)
        self.b_ver.pack(side=tk.LEFT)
        ttk.Button(bot, text="Volver a la consigna original", command=self.original).pack(side=tk.LEFT, padx=6)
        ttk.Button(bot, text="Cerrar", command=self.destroy).pack(side=tk.RIGHT)

    def calcular(self):
        cods = [c for c, v in self.vars.items() if v.get()]
        if not cods:
            messagebox.showinfo("Optimizar", "Marca al menos un producto.", parent=self)
            return
        try:
            max_mm, paso = float(self.var_max.get()), float(self.var_paso.get())
        except (tk.TclError, ValueError):
            messagebox.showerror("Optimizar", "Valores de mm no válidos.", parent=self)
            return
        self.boton.configure(state=tk.DISABLED)
        self.var_res.set("Calculando…")

        def progreso(vuelta, frac):
            self.barra["value"] = frac
            self.var_res.set(f"Calculando… (vuelta {vuelta + 1})")
            self.update()

        try:
            r = neumatico.optimizar(self.app.consigna, self.seccion, self.app.ajustes(), max_mm, paso, cods, progreso)
        finally:
            self.boton.configure(state=tk.NORMAL)
        self.resultado = r
        self.barra["value"] = 1.0
        f = neumatico._f
        mejora = (1 - r.aire_despues / r.aire_antes) * 100 if r.aire_antes else 0
        self.var_res.set(f"Aire entre productos: {f(round(r.aire_antes, 2))} → {f(round(r.aire_despues, 2))} mm²"
                         f"  (−{mejora:.0f} %)     zona aro (aprox.): {f(round(r.aro_antes, 1))} → "
                         f"{f(round(r.aro_despues, 1))} mm²")
        self.tabla.delete(*self.tabla.get_children())
        for p in self.app.consigna.de(self.seccion):
            if p.codigo not in self.vars:
                continue
            d = r.desplazamientos.get(p.codigo, 0.0)
            self.tabla.insert("", tk.END, values=(
                p.codigo, f"{p.trazo_tipo} {f(p.trazo)}", f"{p.trazo_tipo} {f(round(p.trazo + d, 2))}",
                f"{d:+g}" if d else "0", "hacia fuera" if d > 0 else ("hacia el centro" if d < 0 else "—")))
        self.b_ver.configure(state=tk.NORMAL)

    def ver(self):
        if self.resultado:
            neumatico.aplicar_desplazamientos(self.app.consigna, self.resultado.desplazamientos)
            self.app._actualizar_neumatico()

    def original(self):
        neumatico.aplicar_desplazamientos(self.app.consigna, {})
        self.app._actualizar_neumatico()


TABLA_AIRE = (("entre", "Entre (debajo → encima), ESP", 230), ("x0", "Desde (mm desde 0)", 130),
              ("x1", "Hasta (mm desde 0)", 130), ("area", "Área sección (mm²)", 130),
              ("alto", "Altura máx. (mm)", 110), ("vol", "Volumen por lado (cm³)", 150),
              ("zona", "Zona", 110))
TABLA_NEUMATICO = (("prod", "PROD.", 70), ("apel", "Apelación", 110), ("anc", "ANC.", 70),
                   ("esp", "ESP.", 60), ("ang", "ANG.", 60), ("trazo", "TRAZO", 80),
                   ("bint", "Borde int. (mm desde 0)", 150), ("bext", "Borde ext. (mm desde 0)", 150),
                   ("long", "LONG.", 80), ("peso", "PESO", 70))

AYUDA = """CONSIGNA DE NEUMÁTICO (hoja CONSIGNA con tabla PROD. / ANC. / ESP. / TRAZO):
se detecta sola. Cada producto se dibuja desde el 0 (centro) según su TRAZO:
• C = centrado · IN x = borde interior a x mm del centro · EX x = borde exterior a x mm.
• TT (aro) se coloca en ±ENTRE-TRINGLES/2 (entre aros / 2). Lados AR (izquierda) y R (derecha).

AIRE ENTRE PRODUCTOS (vista Plano): cada producto se apoya sobre los anteriores como una lámina
con cierta rigidez: no entra en los rincones de los escalones y el hueco que queda es aire
(rayado rojo). «Rigidez» = radio con el que la goma puentea los escalones (× su espesor);
«Chaflán» = largo de los bordes achaflanados (× espesor). Ajústalos para que el dibujo se
parezca a lo que veis en máquina. «Simular ruletaje» aprieta los productos (radio pequeño)
para ver cuánto aire quedaría tras pasar los apliques. La pestaña «Aire entre productos»
lista cada bolsa: entre qué productos, dónde (mm desde el 0), área y volumen por lado.

PERFIL GENÉRICO: Excel con dos hojas: «Perfil» y «Cotas».
(En CSV: perfil.csv + perfil_cotas.csv en la misma carpeta; separador ; o ,)

HOJA PERFIL — una fila por punto, en orden:
• Contorno: nombre del contorno (Exterior, Interior…). Los contornos dentro de otro son huecos.
• Punto: nombre del punto (E1, A…). Se usa en las cotas.
• X, Y: coordenadas en mm.
  — o bien Longitud y Angulo (grados, 0 = derecha, 90 = arriba) desde el punto anterior.
• Radio: redondeo de la esquina en ese punto (opcional).
• Tipo: P = punto (por defecto), C = círculo/taladro (X, Y = centro + Diametro).
• Cerrado: NO para un perfil abierto (por defecto se cierra).

HOJA COTAS — una fila por cota de la consigna:
• Nombre, Tipo: H horizontal, V vertical, L alineada, D diámetro, R radio.
• Desde, Hasta: nombres de puntos (D y R solo usan Desde).
• Nominal, Tol+, Tol- (o una sola columna Tol para ±).
• Medido (opcional): la app marca OK (verde) o NOK (rojo).
• Offset (opcional): separación de la línea de cota; negativo = al otro lado.

Si el perfil dibujado no cumple la cota nominal, la cota sale en ámbar con aviso.
Exporta a PDF, PNG, SVG o DXF (AutoCAD).

La app no se conecta a internet: tus datos no salen de este equipo."""


if __name__ == "__main__":
    App().mainloop()
