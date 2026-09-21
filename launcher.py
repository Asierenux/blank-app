import os
import sys
import threading
import time
import webbrowser


def resource_path(relative_path: str) -> str:
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def open_browser() -> None:
    time.sleep(3)
    webbrowser.open("http://localhost:8501")


if __name__ == "__main__":
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")

    threading.Thread(target=open_browser, daemon=True).start()

    # Inside a PyInstaller bundle, streamlit.__file__ lives under a temp
    # extraction dir (no "site-packages" in the path), so Streamlit's
    # own heuristic always treats this as "development mode" - which
    # then refuses to let the CLI set server.port. The CLI reparses
    # config from _config_options_template on every run (discarding
    # plain set_option calls), so the override has to live on the
    # template's ConfigOption itself to survive that.
    from streamlit import config as st_config

    st_config._config_options_template["global.developmentMode"].set_value(
        False, "launcher.py"
    )

    from streamlit.web import cli as stcli

    sys.argv = [
        "streamlit",
        "run",
        resource_path("streamlit_app.py"),
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    sys.exit(stcli.main())
