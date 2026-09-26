# 🛒 Comparador de precios de supermercados

App en Streamlit que busca tu lista de la compra en las tiendas online de
**Mercadona, Dia, Consum y Carrefour** y te dice, artículo por artículo, dónde
es más barato. También calcula cuánto costaría la cesta completa en cada
supermercado y cuánto si combinas tiendas.

- Compara por **precio por kg / litro / unidad** (más justo cuando los envases
  son distintos) o por precio del envase.
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

## Estructura

- `streamlit_app.py` – interfaz.
- `supermercados/stores.py` – un conector por supermercado. Para añadir otro,
  crea una subclase de `Store` con un método `search()` y regístrala en `ALL_STORES`.
- `supermercados/compare.py` – búsqueda en paralelo, ordenación y resumen de la cesta.
- `supermercados/demo.py` – datos de ejemplo.

## Tests

```
pip install pytest
python -m pytest
```
