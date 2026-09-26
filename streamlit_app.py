import pandas as pd
import streamlit as st

from supermercados import ALL_STORES, get_store
from supermercados.compare import Item, basket_summary, search_all, sort_products, to_dataframe
from supermercados.demo import demo_search
from supermercados.quality import LABEL_TO_KEY, QUALITIES
from supermercados.stores import Mercadona

st.set_page_config(page_title="Comparador de supermercados", page_icon="🛒", layout="wide")

st.title("🛒 Comparador de precios de supermercados")
st.write(
    "Escribe tu lista de la compra, elige la calidad que quieres para cada artículo "
    "(eco/bio, camperos, integral…) y la app busca en las tiendas online dónde es más barato."
)

ECO = QUALITIES["eco"].label
QUALITY_LABELS = [q.label for q in QUALITIES.values()]

# --- Opciones ---------------------------------------------------------------
with st.sidebar:
    st.header("Opciones")
    store_names = {cls.name: key for key, cls in ALL_STORES.items()}
    selected = st.multiselect("Supermercados", list(store_names), default=list(store_names))
    eco_basket = st.toggle(
        "🌱 Cesta eco / bio",
        help="Exige producto ecológico en todos los artículos de la lista.",
    )
    warehouse = st.selectbox(
        "Zona (precios de Mercadona)",
        list(Mercadona.WAREHOUSES),
        format_func=Mercadona.WAREHOUSES.get,
    )
    by_unit = st.radio(
        "Comparar por",
        ["Precio por kg / litro / unidad", "Precio del envase"],
        help="El precio por kg o litro es más justo cuando los envases tienen tamaños distintos.",
    ).startswith("Precio por")
    limit = st.slider("Resultados por supermercado", 3, 30, 10)
    strict = st.checkbox(
        "Solo productos que contengan todas las palabras buscadas",
        value=True,
        help="Filtra resultados poco relacionados con la búsqueda.",
    )
    demo = st.toggle(
        "Modo demo (precios inventados)",
        value=False,
        help="Para probar la app sin conexión. Desactívalo para ver precios reales.",
    )
    st.caption(
        "Los precios reales se obtienen en el momento de las webs de cada tienda. "
        "Pueden variar según tu código postal y no incluyen gastos de envío."
    )

# --- Lista de la compra -----------------------------------------------------
st.subheader("📝 Lista de la compra")
st.caption(
    "Añade filas con ➕. En **Calidad** puedes elegir una o varias (p. ej. arroz 🌱 Eco + 🌾 Integral). "
    "Los huevos ecológicos cuentan también como camperos."
)
if "lista" not in st.session_state:
    st.session_state.lista = pd.DataFrame(
        [
            {"Artículo": "leche entera", "Cantidad": 2, "Calidad": []},
            {"Artículo": "huevos", "Cantidad": 1, "Calidad": [QUALITIES["campero"].label]},
            {"Artículo": "aceite de oliva", "Cantidad": 1, "Calidad": [QUALITIES["virgen_extra"].label]},
            {"Artículo": "arroz", "Cantidad": 1, "Calidad": [ECO]},
        ]
    )
lista = st.data_editor(
    st.session_state.lista,
    num_rows="dynamic",
    hide_index=True,
    use_container_width=True,
    key="lista_editor",
    column_config={
        "Artículo": st.column_config.TextColumn(required=True, width="medium"),
        "Cantidad": st.column_config.NumberColumn(min_value=1, step=1, default=1, width="small"),
        "Calidad": st.column_config.MultiselectColumn(options=QUALITY_LABELS, width="large"),
    },
)

items = []
for row in lista.to_dict("records"):
    name = str(row.get("Artículo") or "").strip()
    if not name:
        continue
    labels = list(row.get("Calidad") or [])
    required = [LABEL_TO_KEY[label] for label in labels if label in LABEL_TO_KEY]
    if eco_basket and "eco" not in required:
        required.append("eco")
    qty = row.get("Cantidad")
    items.append(Item(name, float(qty) if pd.notna(qty) and qty else 1, required))


@st.cache_data(ttl=3600, show_spinner=False)
def cached_search(store_key: str, query: str, limit: int, warehouse: str):
    return get_store(store_key).search(query, limit=limit, warehouse=warehouse)


def search_fn(store_name: str, query: str):
    if demo:
        return demo_search(store_name, query, limit)
    return cached_search(store_names[store_name], query, limit, warehouse)


if not st.button("Comparar precios", type="primary", disabled=not (items and selected)):
    st.stop()

with st.spinner(f"Buscando {len(items)} artículo(s) en {len(selected)} supermercado(s)…"):
    results = search_all(items, selected, search_fn, strict=strict)

if demo:
    st.info("Modo demo: los precios son inventados. Desactívalo en la barra lateral para ver precios reales.")

errors = {store: msg for r in results for store, msg in r.errors.items()}
if errors:
    st.warning(
        "No se pudo consultar: " + ", ".join(sorted(errors))
        + ". Puede que la tienda haya cambiado su web o esté bloqueando las consultas."
    )
    with st.expander("Detalles de los errores"):
        for msg in errors.values():
            st.code(msg)

if not any(r.products for r in results):
    st.error("No se encontró ningún producto.")
    st.stop()

# --- Resumen de la cesta ----------------------------------------------------
summary = basket_summary(results, by_unit)
st.subheader("🏆 Resumen: dónde comprar cada artículo")
st.dataframe(
    summary["rows"],
    hide_index=True,
    use_container_width=True,
    column_config={
        "Precio (€)": st.column_config.NumberColumn(format="%.2f €"),
        "Subtotal (€)": st.column_config.NumberColumn(format="%.2f €"),
        "Calidad pedida": st.column_config.MultiselectColumn(),
    },
)

if summary["totals"]:
    ranking = sorted(summary["totals"].items(), key=lambda x: (summary["missing"].get(x[0], 0), x[1]))
    cols = st.columns(min(len(ranking) + 1, 4))
    cells = [("Combinando tiendas", summary["mixed_total"], 0)] + [
        (f"Todo en {store}", total, summary["missing"].get(store, 0)) for store, total in ranking
    ]
    for i, (label, total, missing) in enumerate(cells):
        cols[i % len(cols)].metric(
            label,
            f"{total:.2f} €",
            help=f"Faltan {missing} artículo(s) en esta tienda" if missing else None,
        )
        if missing:
            cols[i % len(cols)].caption(f"⚠️ faltan {missing} artículo(s)")
    st.caption("Los totales usan el producto más barato de cada artículo que cumple la calidad pedida, por la cantidad indicada.")

# --- Detalle por artículo ---------------------------------------------------
st.subheader("🔎 Detalle por artículo")
for r in results:
    products = sort_products(r.products, by_unit)
    wanted = " + ".join(QUALITIES[k].label for k in r.item.required)
    title = f"{r.query}{' · ' + wanted if wanted else ''} — {len(products)} resultado(s)"
    with st.expander(title, expanded=len(results) == 1):
        if r.discarded_quality:
            st.caption(f"Se descartaron {r.discarded_quality} producto(s) que no cumplen la calidad pedida.")
        if not products:
            st.info("No se encontraron productos. Prueba con otras palabras o quita algún requisito de calidad.")
            continue
        best = products[0]
        st.success(
            f"Más barato: **{best.name}** en **{best.store}** — "
            f"{best.price:.2f} € ({best.unit_price_label})"
        )
        df = to_dataframe(products)
        st.dataframe(
            df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Imagen": st.column_config.ImageColumn(width="small"),
                "Enlace": st.column_config.LinkColumn(display_text="Ver"),
                "Precio (€)": st.column_config.NumberColumn(format="%.2f €"),
                "Precio unidad": st.column_config.NumberColumn(format="%.2f €"),
                "Calidad": st.column_config.MultiselectColumn(),
            },
            column_order=[
                c
                for c in ["Imagen", "Supermercado", "Producto", "Precio (€)", "Precio unidad", "Unidad", "Calidad", "Enlace"]
                if df[c].map(lambda v: bool(v) if isinstance(v, list) else pd.notna(v)).any()
            ],
        )
