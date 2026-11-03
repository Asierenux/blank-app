"""Pruebas del núcleo (funcionan en Linux y Windows)."""
import os
import shutil
import sys
import time
from pathlib import Path

import psutil
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HMI_WATCHDOG_HOME", str(tmp_path / "data"))
    import watchdog_core as core

    # Simulamos la HMI con una copia de un programa que se queda "esperando"
    if os.name == "nt":
        src, args = r"C:\Windows\System32\PING.EXE", "-n 600 127.0.0.1"
    else:
        src, args = shutil.which("sleep"), "600"
    if not src or not os.path.exists(src):
        pytest.skip("no hay programa para simular la HMI")
    fake = tmp_path / ("fakehmi.exe" if os.name == "nt" else "fakehmi")
    shutil.copy(src, fake)
    os.chmod(fake, 0o755)
    cfg = core.Config(exe_path=str(fake), args=args, check_interval_s=1,
                      restart_delay_s=0, startup_delay_s=0, detect_hang=False,
                      loop_max_restarts=3, loop_window_min=10, loop_cooldown_min=1)
    yield core, cfg
    for p in psutil.process_iter(["exe"]):
        if p.info["exe"] and os.path.normcase(p.info["exe"]) == os.path.normcase(str(fake)):
            p.kill()


def wait_for(cond, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.1)
    return False


def test_config_and_state_roundtrip(env):
    core, cfg = env
    cfg.save()
    assert core.Config.load() == cfg
    st = core.State(restart_count=7, last_restart="x")
    st.save()
    assert core.State.load().restart_count == 7


def test_launch_restart_counter_and_loop_protection(env):
    core, cfg = env
    wd = core.Watchdog(cfg, core.State())
    wd.start()
    try:
        assert wait_for(lambda: core.find_process(cfg.exe_path) is not None)
        assert wd.state.boot_launches == 1 and wd.state.restart_count == 0

        for n in (1, 2, 3):
            core.find_process(cfg.exe_path).kill()
            assert wait_for(lambda: wd.state.restart_count == n), wd.snapshot()["events"]
            assert wait_for(lambda: wd.snapshot()["status"] == core.Status.RUNNING)

        # Persistido en disco
        assert core.State.load().restart_count == 3
        assert core.State.load().last_reason == "Cerrada"

        # 4º cierre en la ventana -> bloqueo anti-bucle, sin relanzar
        core.find_process(cfg.exe_path).kill()
        assert wait_for(lambda: wd.snapshot()["status"] == core.Status.LOOP_BLOCK)
        time.sleep(2)
        assert core.find_process(cfg.exe_path) is None
        assert wd.state.restart_count == 3

        # Reanudar quita el bloqueo y relanza
        wd.resume()
        assert wait_for(lambda: wd.state.restart_count == 4)

        rows = core.read_history()
        assert any("REINICIO #4" in r[1] for r in rows)
    finally:
        wd.stop()


def test_pause_does_not_restart(env):
    core, cfg = env
    wd = core.Watchdog(cfg, core.State())
    wd.start()
    try:
        assert wait_for(lambda: core.find_process(cfg.exe_path) is not None)
        wd.pause(1)
        core.find_process(cfg.exe_path).kill()
        time.sleep(2.5)
        assert core.find_process(cfg.exe_path) is None
        assert wd.snapshot()["status"] == core.Status.PAUSED
        assert wd.snapshot()["last_error"] == ""
        assert wd.snapshot()["pid"] is None
        wd.resume()
        assert wait_for(lambda: wd.state.restart_count == 1)
    finally:
        wd.stop()


def test_already_running_is_not_counted(env):
    core, cfg = env
    core.launch(cfg)
    assert wait_for(lambda: core.find_process(cfg.exe_path) is not None)
    wd = core.Watchdog(cfg, core.State())
    wd.start()
    try:
        assert wait_for(lambda: wd.snapshot()["status"] == core.Status.RUNNING)
        time.sleep(1.5)
        assert wd.state.boot_launches == 0 and wd.state.restart_count == 0
    finally:
        wd.stop()


def test_fmt_duration():
    import watchdog_core as core
    assert core.fmt_duration(3661) == "01:01:01"
    assert core.fmt_duration(90061) == "1d 01h 01m"
