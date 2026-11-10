"""Línea de comandos.

Ejemplos:
    # Entrenar y guardar modelo
    python -m gocator_inspector entrenar --buenas ej/buenas --malas ej/malas --modelo pieza.joblib

    # Separar un directorio con un modelo guardado
    python -m gocator_inspector separar --modelo pieza.joblib --entrada lote_123 --salida resultado

    # Todo en uno (entrena y separa)
    python -m gocator_inspector separar --buenas ej/buenas --malas ej/malas --entrada lote_123 --salida resultado
"""

from __future__ import annotations

import argparse
import sys

from . import Inspector, PreprocessConfig, list_images, sort_files


def _progress(frac: float, msg: str) -> None:
    sys.stderr.write(f"\r[{frac * 100:5.1f}%] {msg[:70]:<70}")
    if frac >= 1:
        sys.stderr.write("\n")
    sys.stderr.flush()


def _train(args) -> Inspector:
    cfg = PreprocessConfig(long_side=args.tamano, normalization=args.normalizacion,
                           level_plane=args.nivelar, invalid_zero=args.cero_invalido,
                           invalid_max=args.max_sin_dato, remove_overlays=not args.mantener_anotaciones)
    insp = Inspector(cfg)
    good = list_images(args.buenas, args.recursivo)
    bad = list_images(args.malas, args.recursivo) if args.malas else []
    print(f"Entrenando con {len(good)} buenas y {len(bad)} malas…")
    rep = insp.fit(good, bad, progress=_progress)
    for n in rep.notes:
        print("  ·", n)
    conf = rep.confusion(insp.thresholds)
    if conf is not None and rep.n_bad:
        print("\nValidación cruzada sobre los ejemplos:\n", conf.to_string(), "\n", sep="")
    return insp


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="gocator_inspector", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def train_args(p, required: bool):
        p.add_argument("--buenas", required=required, help="Directorio con imágenes buenas")
        p.add_argument("--malas", help="Directorio con imágenes malas")
        p.add_argument("--tamano", type=int, default=768, help="Lado largo tras redimensionar")
        p.add_argument("--normalizacion", choices=["none", "median", "robust"], default="median")
        p.add_argument("--nivelar", action="store_true", help="Quitar inclinación (ajuste de plano)")
        p.add_argument("--cero-invalido", action="store_true", help="Fondo negro (<= --max-sin-dato) = sin dato")
        p.add_argument("--max-sin-dato", type=float, default=0.0, help="Valor máx. 'sin dato' (8 para JPG)")
        p.add_argument("--mantener-anotaciones", action="store_true",
                       help="No borrar las cajas/textos de color del Gocator")
        p.add_argument("--recursivo", action="store_true", help="Buscar en subcarpetas")

    pt = sub.add_parser("entrenar", help="Entrena y guarda un modelo")
    train_args(pt, True)
    pt.add_argument("--modelo", required=True, help="Archivo .joblib de salida")

    ps = sub.add_parser("separar", help="Clasifica y separa un directorio")
    train_args(ps, False)
    ps.add_argument("--modelo", help="Modelo .joblib (si no, se entrena con --buenas/--malas)")
    ps.add_argument("--entrada", required=True, help="Directorio a inspeccionar")
    ps.add_argument("--salida", required=True, help="Directorio de resultados")
    ps.add_argument("--mover", action="store_true", help="Mover en vez de copiar")
    ps.add_argument("--umbral-prob", type=float, help="Prob. mínima para MALA (por defecto, la sugerida)")
    ps.add_argument("--umbral-anomalia", type=float, help="Anomalía mínima para MALA (por defecto 1.0)")

    args = ap.parse_args(argv)
    if args.cmd == "entrenar":
        insp = _train(args)
        insp.save(args.modelo)
        print(f"Modelo guardado en {args.modelo}")
        return 0

    if args.modelo:
        insp = Inspector.load(args.modelo)
    elif args.buenas:
        insp = _train(args)
    else:
        ap.error("Indica --modelo o --buenas (y opcionalmente --malas)")
    thr = insp.thresholds
    if args.umbral_prob is not None:
        thr.bad_prob = args.umbral_prob
        thr.doubt_prob = min(thr.doubt_prob, args.umbral_prob)
    if args.umbral_anomalia is not None:
        thr.bad_anomaly = args.umbral_anomalia
        thr.doubt_anomaly = min(thr.doubt_anomaly, args.umbral_anomalia)

    paths = list_images(args.entrada, args.recursivo)
    df = insp.predict(paths, progress=_progress, thr=thr)
    df = sort_files(df, args.salida, move=args.mover)
    counts = df["decision"].value_counts()
    print(f"\nResultado en {args.salida}: " + ", ".join(f"{k}: {v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
