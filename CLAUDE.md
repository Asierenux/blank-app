# Instrucciones para Claude

Proyecto: herramienta para crear piezas imprimibles en una Bambu Lab P2S (256×256×256 mm). Idioma de la UI y docs: español.

## Cuando el usuario pida replicar una pieza (fotos/planos/medidas)
- Crea `modelos/<nombre_snake>.py` copiando `modelos/_plantilla.py` (NOMBRE, DESCRIPCION, PARAMS, build).
- Unidades mm, Z arriba, apoyo en Z=0, orientación pensada para imprimir con mínimos soportes.
- Todas las cotas relevantes como PARAMS. Si falta una medida, pídela o estímala a partir de una
  referencia visible y dilo explícitamente en DESCRIPCION.
- Holguras: encaje a presión +0.1, deslizante +0.2, holgado +0.3, tornillo M3→3.3, M4→4.3, M5→5.3.
- Paredes ≥ 1.2 mm (3 perímetros con boquilla 0.4). Evitar voladizos > 45º sin soportes.
- Usa printlab.geometry y manifold3d (booleanas robustas → malla cerrada). Para perfiles 2D con
  puntos de orientación incierta usa `CrossSection.hull_points` o asegura sentido antihorario.
- Si devuelves varias piezas usa un dict {"nombre": Manifold} y sepáralas en X.
- Verifica: `python -m pytest -q tests` (comprueba que todos los modelos son watertight).
