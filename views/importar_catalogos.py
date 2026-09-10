import csv
import io

import streamlit as st

import db
import ui

ui.page_header(
    "upload_file", "Importar catálogos",
    "Carga aquí los catálogos maestros exportados de vuestro Excel (TAB_MAE de "
    "MDV_EPQL.xlsm): códigos CQ, dimensiones y códigos de operario. Los ficheros "
    "se procesan localmente en tu propia instancia; esta app no envía ni almacena "
    "estos datos en ningún sitio fuera de tu base de datos local.",
)

tab_cq, tab_dim, tab_op = st.tabs(
    [":material/error: Códigos CQ", ":material/inventory_2: Dimensiones", ":material/person: Códigos de operario"]
)

with tab_cq:
    st.markdown(
        "CSV con columnas **`codigo,familia`** (familia = `NCNA` o `H2`). "
        "Este catálogo sustituye/completa la lista por defecto del Anexo 5 en el "
        "desplegable de CQ del registro de verificación."
    )
    file = st.file_uploader("Fichero CSV de códigos CQ", type=["csv"], key="up_cq")
    if file is not None:
        content = file.getvalue().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        filas = [(row.get("codigo", ""), row.get("familia", "")) for row in reader]
        st.write(f"Se han leído **{len(filas)}** filas del CSV.")
        if st.button("Importar códigos CQ", type="primary"):
            n = db.import_catalogo_cq(filas)
            st.success(f"Importados/actualizados {n} códigos CQ.")
            st.rerun()

    catalogo = db.list_catalogo_cq()
    st.metric("Códigos CQ en el catálogo", len(catalogo))
    if catalogo:
        import pandas as pd
        df_cq = pd.DataFrame([{"Código": c["codigo"], "Familia": c["familia"]} for c in catalogo])
        df_cq.index = [""] * len(df_cq)
        st.table(df_cq)

with tab_dim:
    st.markdown(
        "CSV con columnas **`codigo,designacion`**. Se crean como dimensiones nuevas "
        "(tipo por defecto *Carcasa*, editable después); los códigos ya existentes se omiten."
    )
    tipo_defecto = st.selectbox("Tipo por defecto para las dimensiones importadas", db.TIPOS_PRODUCTO)
    file = st.file_uploader("Fichero CSV de dimensiones", type=["csv"], key="up_dim")
    if file is not None:
        content = file.getvalue().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        filas = [(row.get("codigo", ""), row.get("designacion", "")) for row in reader]
        st.write(f"Se han leído **{len(filas)}** filas del CSV.")
        if st.button("Importar dimensiones", type="primary"):
            n = db.import_dimensiones(filas, tipo_por_defecto=tipo_defecto)
            st.success(f"Importadas {n} dimensiones nuevas (se omiten códigos ya existentes).")
            st.rerun()

    dimensiones = db.list_dimensiones()
    st.metric("Dimensiones en la base de datos", len(dimensiones))

with tab_op:
    st.markdown(
        "CSV con columna **`codigo`** (sólo el código de operario, sin nombre). "
        "Se da de alta un verificador por cada código, usando el propio código como "
        "identificador. Quedan en estado *Pendiente de evaluación* hasta registrar su "
        "test de calificación en la página **Verificadores** (Anexo 1)."
    )
    file = st.file_uploader("Fichero CSV de códigos de operario", type=["csv"], key="up_op")
    if file is not None:
        content = file.getvalue().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        codigos = [row.get("codigo", "") for row in reader]
        st.write(f"Se han leído **{len(codigos)}** códigos del CSV.")
        if st.button("Importar códigos de operario", type="primary"):
            n = db.import_verificadores_codigos(codigos)
            st.success(f"Importados {n} códigos de operario nuevos como verificadores.")
            st.rerun()

    verificadores = db.list_verificadores()
    st.metric("Verificadores en la base de datos", len(verificadores))
