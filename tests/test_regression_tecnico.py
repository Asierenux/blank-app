"""
Prueba de humo (no pytest, un script normal) del flujo de Técnico: entra
como Operario anónimo por defecto, se identifica como Técnico desde el
panel lateral, recorre todas las páginas de Técnico sin excepciones, y
vuelve a modo Operario.

Uso: python tests/test_regression_tecnico.py
(usa una base de datos temporal propia: no toca data/mdv.db)
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from streamlit.testing.v1 import AppTest

import db

db.DB_PATH = Path(tempfile.mkdtemp()) / "test_tecnico.db"
db.get_conn.clear()
db.init_db(db.get_conn())

if db.count_usuarios() == 0:
    db.add_usuario("tecnico1", "password123", "Técnico")

if not db.list_maquinas():
    db.add_maquina("MAC-1", "MAC")

print("Seed OK")

# --- Test 1: with a técnico already existing, landing goes straight to
#     Operario mode (no login screen, no bootstrap form) -------------------
at = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "streamlit_app.py"))
at.run(timeout=15)
assert not at.exception, at.exception
assert at.session_state["auth_user"]["rol"] == "Operario"
assert at.session_state["auth_user"]["id"] is None
print("Test 1 OK: default landing is anonymous Operario, no login required")

# --- Test 2: elevate to técnico via the sidebar form -----------------------
inputs = at.sidebar.text_input
assert len(inputs) >= 2, f"expected user+password inputs in sidebar, got {len(inputs)}"
inputs[0].set_value("tecnico1")
inputs[1].set_value("password123")
submit_btn = next(b for b in at.sidebar.button if "Entrar" in (b.label or ""))
submit_btn.click().run(timeout=15)
assert not at.exception, at.exception
assert at.session_state["auth_user"]["username"] == "tecnico1"
assert at.session_state["auth_user"]["rol"] == "Técnico"
print("Test 2 OK: elevated to técnico via sidebar form")

# --- Test 3: navigate every técnico page ------------------------------------
paginas = [
    "views/inicio.py", "views/maquinas_dimensiones.py", "views/registro_verificacion.py",
    "views/no_conformidades.py", "views/verificadores.py", "views/importar_catalogos.py",
    "views/usuarios.py",
]
for p in paginas:
    at.switch_page(p).run(timeout=15)
    assert not at.exception, f"{p}: {at.exception}"
    print(f"Test 3 OK: {p} renders without exception")

# --- Test 4: drop back to anonymous Operario mode ---------------------------
at.switch_page("views/inicio.py").run(timeout=15)
volver_btn = next(b for b in at.sidebar.button if "Volver a modo Operario" in (b.label or ""))
volver_btn.click().run(timeout=15)
assert not at.exception, at.exception
assert at.session_state["auth_user"]["rol"] == "Operario"
assert at.session_state["auth_user"]["id"] is None
print("Test 4 OK: back to anonymous Operario mode, sees only Registro de verificación")

print("\nALL TESTS PASSED")
