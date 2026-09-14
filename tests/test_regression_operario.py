"""
Prueba de humo (no pytest, un script normal) del flujo completo de
Operario en Registro de verificación: selección de verificador
obligatoria, validación de matrícula de 8 dígitos, guardado, reinicio
del formulario tras guardar, e Historial.

Uso: python tests/test_regression_operario.py
(usa una base de datos temporal propia: no toca data/mdv.db)
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from streamlit.testing.v1 import AppTest

import db

db.DB_PATH = Path(tempfile.mkdtemp()) / "test_operario.db"
db.get_conn.clear()
db.init_db(db.get_conn())

if db.count_usuarios() == 0:
    db.add_usuario("tecnico1", "password123", "Técnico")

if not db.list_maquinas():
    db.add_maquina("MAC-1", "MAC")
maq_id = db.list_maquinas()[0]["id"]

if not db.list_dimensiones():
    db.add_dimension("195/65R15", "Carcasa", "")
dim_id = db.list_dimensiones()[0]["id"]

if not any(a["maquina_id"] == maq_id and a["dimension_id"] == dim_id for a in db.list_asignaciones(solo_activas=True)):
    asig_existente = next(
        a for a in db.list_asignaciones(solo_activas=False)
        if a["maquina_id"] == maq_id and a["dimension_id"] == dim_id
    )
    db.set_activa_asignacion(asig_existente["id"], True)

if not db.list_verificadores():
    db.add_verificador("V001", "2026-01-01", 95.0, "2026-01-01", 0, 1, "")

print("Seed OK")

# --- Test 1: default landing is anonymous Operario -------------------------
at = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "streamlit_app.py"))
at.run(timeout=15)
assert not at.exception, at.exception
assert at.session_state["auth_user"]["rol"] == "Operario"
print("Test 1 OK: default landing is anonymous Operario")

# --- Test 2: registro form requires verificador before continuing ----------
info_texts = [i.value for i in at.info]
assert any("quién está verificando" in t for t in info_texts), f"expected verificador gate, got: {info_texts}"
print("Test 2 OK: registro blocks progress until a verificador is selected")

# --- Test 3: select verificador, fill an invalid matrícula, expect error ---
sel_verif = next(s for s in at.selectbox if s.label and "verifica" in s.label.lower())
sel_verif.set_value("V001").run(timeout=15)
assert not at.exception, at.exception

mat_input = next(t for t in at.text_input if t.label and "Matrícula inicial" in t.label)
mat_input.set_value("123").run(timeout=15)  # invalid: not 8 digits
assert not at.exception, at.exception
error_texts = [e.value for e in at.error]
assert any("8 dígitos" in t for t in error_texts), f"expected 8-digit validation error, got: {error_texts}"
print("Test 3 OK: non-8-digit matrícula is rejected with a clear error")

# --- Test 4: fill a valid 8-digit matrícula, reach summary, save -----------
mat_input = next(t for t in at.text_input if t.label and "Matrícula inicial" in t.label)
mat_input.set_value("04473012").run(timeout=15)
assert not at.exception, at.exception

mat_final_input = next(t for t in at.text_input if t.label == "Matrícula final")
mat_final_input.set_value("04473032").run(timeout=15)
assert not at.exception, at.exception

save_btn = next(b for b in at.button if b.label and "Confirmar y guardar" in b.label)
save_btn.click().run(timeout=15)
assert not at.exception, at.exception
print("Test 4 OK: verificación saved without exception")

# --- Test 5: after saving, the form is reset (back to a clean screen) ------
success_texts = [s.value for s in at.success]
assert any("guardada correctamente" in t for t in success_texts), f"expected success banner, got: {success_texts}"
mat_inputs_after = [t for t in at.text_input if t.label and "Matrícula inicial" in t.label]
assert not mat_inputs_after, f"expected matrícula step to be gone after reset, got: {mat_inputs_after}"
info_texts_after = [i.value for i in at.info]
assert any("quién está verificando" in t for t in info_texts_after), "expected verificador gate to reappear after reset"
print("Test 5 OK: form fully resets to a clean state after saving")

# --- Test 6: Historial page renders for Operario and shows the saved row ---
at.switch_page("views/historial_verificaciones.py").run(timeout=15)
assert not at.exception, at.exception
print("Test 6 OK: Historial page renders for Operario without exception")

print("\nALL TESTS PASSED")
