import streamlit as st

from supermercados import ALL_STORES, get_store
from supermercados.compare import basket_summary, search_all, sort_products, to_dataframe
from supermercados.demo import demo_search
from supermercados.stores import Mercadona

st.set_page_config(page_title="Comparador de supermercados", page_icon="🛒", layout="wide")

st.title("🛒 Comparador de precios de supermercados")
st.write(
    "Escribe tu lista de la compra y la app busca cada artículo en las tiendas online "
    "de los supermercados y te dice dónde es más barato."
)

# --- Opciones ---------------------------------------------------------------
with st.sidebar:
    st.header("Opciones")
    store_names = {cls.name: key for key, cls in ALL_STORES.items()}
    selected = st.multiselect("Supermercados", list(store_names), default=list(store_names))
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
        "Modo demo (datos de ejemplo)",
        value=False,
        help="Útil para probar la app sin conexión o si las tiendas bloquean las consultas.",
    )
    st.caption(
        "Los precios se obtienen de las webs públicas de cada tienda. Pueden variar "
        "según tu código postal y no incluyen gastos de envío."
    )


@st.cache_data(ttl=3600, show_spinner=False)
def cached_search(store_key: str, query: str, limit: int, warehouse: str):
    return get_store(store_key).search(query, limit=limit, warehouse=warehouse)


def search_fn(store_name: str, query: str):
    if demo:
        return demo_search(store_name, query, limit)
    return cached_search(store_names[store_name], query, limit, warehouse)


# --- Lista de la compra -----------------------------------------------------
lista = st.text_area(
    "Lista de la compra (un artículo por línea)",
    value="leche entera\nhuevos\naceite de oliva virgen extra\narroz",
    height=140,
)
queries = [line.strip() for line in lista.splitlines() if line.strip()]

if not st.button("Comparar precios", type="primary", disabled=not (queries and selected)):
    st.stop()

with st.spinner(f"Buscando {len(queries)} artículo(s) en {len(selected)} supermercado(s)…"):
    results = search_all(queries, selected, search_fn, strict=strict)

errors = {store: msg for r in results for store, msg in r.errors.items()}
if errors:
    st.warning(
        "No se pudo consultar: " + ", ".join(sorted(errors))
        + ". Puede que la tienda haya cambiado su web o esté bloqueando las consultas. "
        "Prueba el modo demo para ver cómo funciona la app."
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
    column_config={"Precio (€)": st.column_config.NumberColumn(format="%.2f €")},
)

if summary["totals"]:
    cols = st.columns(len(summary["totals"]) + 1)
    cols[0].metric("Combinando tiendas", f"{summary['mixed_total']:.2f} €")
    for col, (store, total) in zip(cols[1:], sorted(summary["totals"].items(), key=lambda x: x[1])):
        missing = summary["missing"].get(store, 0)
        col.metric(
            f"Todo en {store}",
            f"{total:.2f} €",
            delta=f"faltan {missing} artículo(s)" if missing else None,
            delta_color="off",
        )
    st.caption("Los totales suman el producto más barato encontrado de cada artículo (1 unidad).")

# --- Detalle por artículo ---------------------------------------------------
st.subheader("🔎 Detalle por artículo")
for r in results:
    products = sort_products(r.products, by_unit)
    with st.expander(f"{r.query} — {len(products)} resultado(s)", expanded=len(results) == 1):
        if not products:
            st.info("No se encontraron productos. Prueba con otras palabras.")
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
            },
            column_order=[
                c
                for c in ["Imagen", "Supermercado", "Producto", "Precio (€)", "Precio unidad", "Unidad", "Enlace"]
                if df[c].notna().any()
            ],
        )
