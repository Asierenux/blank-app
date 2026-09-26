# 🛒 Comparador de precios de supermercados

App en Streamlit que busca tu lista de la compra en las tiendas online de
**Mercadona, Dia, Consum, Carrefour, Alcampo y Eroski** con precios reales y
te dice, artículo por artículo, dónde es más barato. También calcula cuánto
costaría la cesta completa en cada supermercado y cuánto si combinas tiendas.

- Compara por **precio por kg / litro / unidad** (más justo cuando los envases
  son distintos) o por precio del envase.
- **Calidad por artículo**: 🌱 eco/bio, 🐔 camperos, 🌾 integral, 🫒 virgen
  extra, 🍚 arroz bomba, 🏷️ D.O./IGP, sin lactosa, sin gluten. Se pueden
  combinar (arroz eco + integral). Los huevos ecológicos cuentan como camperos.
- **Cesta eco/bio**: un interruptor exige producto ecológico en toda la lista.
- Cantidad por artículo para calcular el total de la cesta.
- Elige zona para los precios de Mercadona (varían por almacén).
- Filtra resultados poco relacionados con la búsqueda.
- **Modo demo** con datos de ejemplo para probar la app sin conexión.

> ⚠️ Las tiendas no ofrecen APIs oficiales: la app usa las mismas APIs que sus
> webs. Pueden cambiar o bloquear consultas en cualquier momento; si una tienda
> falla, la app lo indica y sigue con las demás.

## Cómo ejecutarla

```
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Comprobar que las tiendas responden

```
python -m supermercados.check leche
```

Muestra, tienda por tienda, si devuelve precios reales o el error. Si alguna
falla, ese mensaje es lo que hace falta para arreglar su conector.

## Estructura

- `streamlit_app.py` – interfaz.
- `supermercados/stores.py` – un conector por supermercado. Para añadir otro,
  crea una subclase de `Store` con un método `search()` y regístrala en `ALL_STORES`.
- `supermercados/quality.py` – detección de calidades (eco, campero…) por el nombre del producto.
- `supermercados/extract.py` – extractores genéricos de JSON/HTML (Alcampo, Eroski).
- `supermercados/compare.py` – búsqueda en paralelo, ordenación y resumen de la cesta.
- `supermercados/demo.py` – datos de ejemplo.

## Tests

```
pip install pytest
python -m pytest
```
