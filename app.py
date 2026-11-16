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

from perfil_app import core, neumatico  # noqa: E402

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
        self.var_ruletaje = tk.BooleanVar(value=False)

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
                           values=("Plano (semisección)", "Posiciones (TRAZO)", "Sección apilada"))
        cb2.pack(side=tk.LEFT)
        cb2.bind("<<ComboboxSelected>>", lambda e: self.redibujar())
        # Segunda fila: parámetros del aire (solo neumático)
        self.barra_aire = ttk.Frame(self, padding=(6, 0, 6, 6))
        ttk.Label(self.barra_aire, text="Chaflán bordes (× espesor):").pack(side=tk.LEFT)
        for var, de, a in ((self.var_chaflan, 1, 12), (self.var_rigidez, 0.5, 20)):
            if var is self.var_rigidez:
                ttk.Label(self.barra_aire, text="Rigidez goma (radio puente × espesor):").pack(side=tk.LEFT,
                                                                                            padx=(12, 0))
            sp = ttk.Spinbox(self.barra_aire, from_=de, to=a, increment=0.5, width=5, textvariable=var,
                             command=self._actualizar_neumatico)
            sp.pack(side=tk.LEFT, padx=(4, 0))
            sp.bind("<Return>", lambda e: self._actualizar_neumatico())
            sp.bind("<FocusOut>", lambda e: self._actualizar_neumatico())
        ttk.Checkbutton(self.barra_aire, text="Simular ruletaje (apliques)", variable=self.var_ruletaje,
                        command=self._actualizar_neumatico).pack(side=tk.LEFT, padx=(16, 0))
        ttk.Button(self.barra_aire, text="⚙ Optimizar posiciones (±2 mm)…",
                   command=self.dialogo_optimizar).pack(side=tk.LEFT, padx=(16, 0))
        self.var_total_aire = tk.StringVar()
        ttk.Label(self.barra_aire, textvariable=self.var_total_aire, foreground="#b00000",
                  font=("TkDefaultFont", 10, "bold")).pack(side=tk.LEFT, padx=(16, 0))
        ttk.Button(barra, text="Guardar plantilla de ejemplo…",
                   command=self.guardar_plantilla).pack(side=tk.RIGHT)
        ttk.Button(barra, text="? Ayuda", command=self.ayuda).pack(side=tk.RIGHT, padx=4)

        panel = ttk.PanedWindow(self, orient=tk.VERTICAL)
        panel.pack(fill=tk.BOTH, expand=True)

        # Dibujo
        marco_dibujo = ttk.Frame(panel)
        self.fig = Figure(figsize=(8, 6), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=marco_dibujo)
        NavigationToolbar2Tk(self.canvas, marco_dibujo).update()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        panel.add(marco_dibujo, weight=4)

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

        self.estado = tk.StringVar(value="Abre una consigna (.xlsx o .csv) para empezar.  "
                                         "Todo se procesa en este equipo, sin conexión.")
        ttk.Label(self, textvariable=self.estado, anchor=tk.W, padding=(6, 3),
                  relief=tk.SUNKEN).pack(side=tk.BOTTOM, fill=tk.X)

        self._pantalla_inicio()

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
        self.barra_neum.pack_forget()
        self.barra_aire.pack_forget()
        self.pestanas.hide(1)
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
        self.title(f"{APP_NOMBRE} — {os.path.basename(ruta)}")
        self.barra_neum.pack(side=tk.LEFT)
        self.barra_aire.pack(side=tk.TOP, fill=tk.X, after=self.barra)
        self.pestanas.add(self.marco_aire)
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
                f(round(p.borde_int, 3)) if p.borde_int is not None else "",
                f(round(p.borde_ext, 3)) if p.borde_ext is not None else "",
                p.longitud, f(p.peso)))
        info = [f"{k}: {v}" for k, v in cons.cabecera.items() if k in ("DIMENSIÓN", "CBL", "C.A.I.") and v]
        if cons.entre_tringles:
            info.append(f"Entre aros {f(cons.entre_tringles)}")
        # bolsas de aire
        self.tabla_aire.delete(*self.tabla_aire.get_children())
        bolsas = neumatico.bolsas_de_aire(cons, self.var_seccion.get(), self.ajustes())
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
        desp = {p.codigo: p.desplazamiento for p in cons.productos if p.desplazamiento}
        if desp:
            info.insert(0, "PROPUESTA: " + ", ".join(f"{k} {v:+g} mm" for k, v in desp.items()))
        self.estado.set(f"{os.path.basename(self.ruta)}  ·  {len(prods)} productos  ·  " + "  ·  ".join(info))

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
        return neumatico.Ajustes(chaflan=leer(self.var_chaflan, d.chaflan), rigidez=leer(self.var_rigidez, d.rigidez),
                                 ruletaje=self.var_ruletaje.get())

    def redibujar(self):
        if not self.consigna:
            return
        if isinstance(self.consigna, neumatico.ConsignaNeumatico):
            v = self.var_vista.get()
            vista = "plano" if v.startswith("Plano") else ("seccion" if v.startswith("Secc") else "posiciones")
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
                          "que deja menos aire entre productos\n(fuera de la zona del aro), con la rigidez y el "
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
