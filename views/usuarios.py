import pandas as pd
import streamlit as st

import db

st.title(":material/admin_panel_settings: Usuarios")
st.caption(
    "Gestión de accesos: cada usuario tiene un rol (Operario/Técnico) que determina "
    "qué páginas ve. Las contraseñas se guardan con hash + sal, nunca en texto plano."
)

tab_alta, tab_lista = st.tabs([":material/add: Nuevo usuario", ":material/checklist: Usuarios existentes"])

with tab_alta:
    with st.form("nuevo_usuario"):
        c1, c2 = st.columns(2)
        username = c1.text_input("Usuario")
        rol = c2.selectbox("Rol", db.ROLES)
        c3, c4 = st.columns(2)
        password = c3.text_input("Contraseña", type="password")
        password2 = c4.text_input("Repite la contraseña", type="password")
        submitted = st.form_submit_button("Crear usuario", type="primary")
        if submitted:
            existentes = {u["username"] for u in db.list_usuarios()}
            if not username.strip() or not password:
                st.error("Usuario y contraseña son obligatorios.")
            elif username.strip() in existentes:
                st.error("Ya existe un usuario con ese nombre.")
            elif len(password) < 6:
                st.error("La contraseña debe tener al menos 6 caracteres.")
            elif password != password2:
                st.error("Las contraseñas no coinciden.")
            else:
                db.add_usuario(username, password, rol)
                st.success(f"Usuario '{username}' creado con rol {rol}.")
                st.rerun()

with tab_lista:
    usuarios = db.list_usuarios()
    if not usuarios:
        st.info("No hay usuarios.")
    else:
        st.dataframe(
            pd.DataFrame([
                {"Usuario": u["username"], "Rol": u["rol"], "Fecha de alta": u["fecha_creacion"]}
                for u in usuarios
            ]),
            use_container_width=True, hide_index=True,
        )

        st.divider()
        st.subheader("Cambiar rol / contraseña / eliminar")
        opciones = {f"{u['username']} ({u['rol']})": u["id"] for u in usuarios}
        sel = st.selectbox("Usuario", list(opciones.keys()))
        usuario_id = opciones[sel]
        usuario_actual = next(u for u in usuarios if u["id"] == usuario_id)

        c1, c2 = st.columns(2)
        with c1:
            nuevo_rol = st.selectbox(
                "Nuevo rol", db.ROLES, index=db.ROLES.index(usuario_actual["rol"]), key="nuevo_rol",
            )
            if st.button("Aplicar rol"):
                db.cambiar_rol_usuario(usuario_id, nuevo_rol)
                st.success("Rol actualizado.")
                st.rerun()
        with c2:
            nueva_password = st.text_input("Nueva contraseña", type="password", key="nueva_pw")
            if st.button("Cambiar contraseña"):
                if len(nueva_password) < 6:
                    st.error("La contraseña debe tener al menos 6 caracteres.")
                else:
                    db.cambiar_password_usuario(usuario_id, nueva_password)
                    st.success("Contraseña actualizada.")

        st.divider()
        if len(usuarios) > 1:
            if st.button(":material/delete: Eliminar este usuario", type="secondary"):
                db.eliminar_usuario(usuario_id)
                st.success("Usuario eliminado.")
                st.rerun()
        else:
            st.caption("No se puede eliminar el último usuario: te quedarías sin acceso a la app.")
