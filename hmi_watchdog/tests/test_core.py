"""Pruebas del núcleo (funcionan en Linux y Windows)."""
import json
import os
import shutil
import sys
import time
from pathlib import Path

import psutil
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _fake_source():
    """Programa que se queda 'esperando', para simular una HMI."""
    if os.name == "nt":
        return r"C:\Windows\System32\PING.EXE", "-n 600 127.0.0.1"
    return shutil.which("sleep"), "600"


def make_fake_exe(folder: Path, name: str = "hmi") -> str:
    src, _ = _fake_source()
    if not src or not os.path.exists(src):
        pytest.skip("no hay programa para simular la HMI")
    folder.mkdir(parents=True, exist_ok=True)
    fake = folder / (f"{name}.exe" if os.name == "nt" else name)
    shutil.copy(src, fake)
    os.chmod(fake, 0o755)
    return str(fake)


@pytest.fixture()
def core(tmp_path, monkeypatch):
    monkeypatch.setenv("HMI_WATCHDOG_HOME", str(tmp_path / "data"))
    import watchdog_core
    yield watchdog_core
    for p in psutil.process_iter(["exe"]):
        exe = p.info["exe"] or ""
        if str(tmp_path) in exe:
            p.kill()


def base_cfg(core, *apps):
    return core.Config(apps=list(apps), check_interval_s=1, restart_delay_s=0,
                       startup_delay_s=0, launch_gap_s=0, detect_hang=False,
                       loop_max_restarts=3, loop_window_min=10, loop_cooldown_min=1)


def make_app(core, tmp_path, sub="a", name="HMI A"):
    _, args = _fake_source()
    return core.AppConfig(name=name, exe_path=make_fake_exe(tmp_path / sub), args=args)


def wait_for(cond, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.1)
    return False


def test_config_and_state_roundtrip(core, tmp_path):
    cfg = base_cfg(core, make_app(core, tmp_path))
    cfg.save()
    loaded = core.Config.load()
    assert loaded == cfg
    assert isinstance(loaded.apps[0], core.AppConfig)
    st = core.State(restart_count=7, last_restart="x")
    st.save("abc")
    assert core.State.load("abc").restart_count == 7


def test_migration_from_single_app_config(core, tmp_path):
    exe = make_fake_exe(tmp_path / "old")
    data = core.data_dir()
    (data / "config.json").write_text(json.dumps({"exe_path": exe, "args": "600", "pin": "1"}))
    (data / "state.json").write_text(json.dumps({"restart_count": 9}))
    cfg = core.Config.load()
    assert len(cfg.apps) == 1 and cfg.apps[0].exe_path == exe and cfg.pin == "1"
    assert core.State.load(cfg.apps[0].id).restart_count == 9
    assert core.Config.load().apps[0].id == cfg.apps[0].id  # guardado tras migrar


def test_launch_restart_counter_and_loop_protection(core, tmp_path):
    app = make_app(core, tmp_path)
    cfg = base_cfg(core, app)
    wd = core.Watchdog(cfg, app, core.State())
    wd.start()
    try:
        assert wait_for(lambda: core.find_process(app.exe_path) is not None)
        assert wd.state.boot_launches == 1 and wd.state.restart_count == 0

        for n in (1, 2, 3):
            core.find_process(app.exe_path).kill()
            assert wait_for(lambda: wd.state.restart_count == n), wd.snapshot()["events"]
            assert wait_for(lambda: wd.snapshot()["status"] == core.Status.RUNNING)

        assert core.State.load(app.id).restart_count == 3
        assert core.State.load(app.id).last_reason == "Cerrada"

        # 4º cierre en la ventana -> bloqueo anti-bucle, sin relanzar
        core.find_process(app.exe_path).kill()
        assert wait_for(lambda: wd.snapshot()["status"] == core.Status.LOOP_BLOCK)
        time.sleep(2)
        assert core.find_process(app.exe_path) is None
        assert wd.state.restart_count == 3

        wd.resume()
        assert wait_for(lambda: wd.state.restart_count == 4)
        rows = core.read_history()
        assert any(r[1] == "HMI A" and "REINICIO #4" in r[2] for r in rows)
    finally:
        wd.stop()


def test_pause_does_not_restart(core, tmp_path):
    app = make_app(core, tmp_path)
    wd = core.Watchdog(base_cfg(core, app), app, core.State())
    wd.start()
    try:
        assert wait_for(lambda: core.find_process(app.exe_path) is not None)
        wd.pause(1)
        core.find_process(app.exe_path).kill()
        time.sleep(2.5)
        assert core.find_process(app.exe_path) is None
        snap = wd.snapshot()
        assert snap["status"] == core.Status.PAUSED
        assert snap["last_error"] == "" and snap["pid"] is None
        wd.resume()
        assert wait_for(lambda: wd.state.restart_count == 1)
    finally:
        wd.stop()


def test_already_running_is_not_counted(core, tmp_path):
    app = make_app(core, tmp_path)
    core.launch(app)
    assert wait_for(lambda: core.find_process(app.exe_path) is not None)
    wd = core.Watchdog(base_cfg(core, app), app, core.State())
    wd.start()
    try:
        assert wait_for(lambda: wd.snapshot()["status"] == core.Status.RUNNING)
        time.sleep(1.5)
        assert wd.state.boot_launches == 0 and wd.state.restart_count == 0
    finally:
        wd.stop()


def test_two_apps_same_exe_name_different_folders(core, tmp_path):
    """Dos HMI que se llaman igual (hmi.exe) en carpetas distintas."""
    a = make_app(core, tmp_path, "linea1", "Perfilómetro L1")
    b = make_app(core, tmp_path, "linea2", "Perfilómetro L2")
    assert os.path.basename(a.exe_path) == os.path.basename(b.exe_path)
    cfg = base_cfg(core, a, b)
    sup = core.Supervisor(cfg)
    sup.start()
    try:
        assert wait_for(lambda: core.find_process(a.exe_path) and core.find_process(b.exe_path))
        pa, pb = core.find_process(a.exe_path), core.find_process(b.exe_path)
        assert pa.pid != pb.pid
        # nombre repetido -> no se permite la comparación por nombre
        assert sup.get(a.id).name_fallback is False

        # Cerrar SOLO la de la línea 2: solo su contador sube
        pb.kill()
        assert wait_for(lambda: sup.get(b.id).state.restart_count == 1)
        time.sleep(1.5)
        assert sup.get(a.id).state.restart_count == 0
        assert core.find_process(a.exe_path).pid == pa.pid  # la L1 no se tocó

        snaps = sup.snapshots()
        assert [s["name"] for s in snaps] == ["Perfilómetro L1", "Perfilómetro L2"]
        assert any("Perfilómetro L2: REINICIO #1" in e for e in sup.events())

        # Desactivar una app deja de vigilarla
        b.enabled = False
        sup.apply(cfg)
        assert sup.get(b.id) is None and len(sup.snapshots()) == 1
    finally:
        sup.stop()


def test_duplicate_paths_detected(core, tmp_path):
    exe = make_fake_exe(tmp_path / "x")
    cfg = base_cfg(core, core.AppConfig(name="1", exe_path=exe),
                   core.AppConfig(name="2", exe_path=exe.upper() if os.name == "nt" else exe))
    assert cfg.duplicate_paths()


def test_fmt_duration(core):
    assert core.fmt_duration(3661) == "01:01:01"
    assert core.fmt_duration(90061) == "1d 01h 01m"
