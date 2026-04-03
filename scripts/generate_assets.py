from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = REPO_ROOT / "docs" / "assets"
HOST = "127.0.0.1"

CAPTURES = [
    {
        "path": "/",
        "output": "home-page.png",
        "viewport": {"width": 1440, "height": 1250},
    },
    {
        "path": "/workflows/wf-invoice-3001",
        "output": "workflow-detail.png",
        "viewport": {"width": 1440, "height": 1500},
    },
    {
        "path": "/workflows/wf-invoice-3001/replay",
        "output": "replay-timeline.png",
        "viewport": {"width": 1440, "height": 1600},
    },
    {
        "path": "/incidents/inc_evt_wf_3001_05",
        "output": "incident-view.png",
        "viewport": {"width": 1440, "height": 1500},
    },
    {
        "path": "/incidents/inc_evt_wf_3001_05/evidence-pack",
        "output": "evidence-pack.png",
        "viewport": {"width": 1440, "height": 1500},
    },
]


def pick_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


def wait_for_server(base_url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}/", timeout=1.0)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for asset capture server at {base_url}")


def ensure_chromium() -> None:
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            browser.close()
            return
    except Exception as exc:  # pragma: no cover - depends on local browser state
        if "Executable doesn't exist" not in str(exc):
            raise

    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        cwd=REPO_ROOT,
        check=True,
    )


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    ensure_chromium()

    with tempfile.TemporaryDirectory(prefix="agent-activity-graph-assets-") as tmpdir:
        db_path = Path(tmpdir) / "assets.db"
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite:///{db_path}"
        env["PYTHONPATH"] = str(REPO_ROOT / "src")

        subprocess.run(
            [sys.executable, "-m", "agent_activity_graph.demo.seed"],
            cwd=REPO_ROOT,
            env=env,
            check=True,
        )

        port = pick_port()
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "agent_activity_graph.api.app:create_app",
                "--factory",
                "--host",
                HOST,
                "--port",
                str(port),
            ],
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )

        try:
            base_url = f"http://{HOST}:{port}"
            wait_for_server(base_url)

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    for capture in CAPTURES:
                        context = browser.new_context(
                            color_scheme="light",
                            viewport=capture["viewport"],
                        )
                        page = context.new_page()
                        try:
                            page.goto(f"{base_url}{capture['path']}", wait_until="networkidle")
                            page.screenshot(
                                path=str(ASSET_DIR / capture["output"]),
                                full_page=False,
                            )
                            print((ASSET_DIR / capture["output"]).relative_to(REPO_ROOT))
                        finally:
                            page.close()
                            context.close()
                finally:
                    browser.close()
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:  # pragma: no cover - defensive
                server.kill()
                server.wait(timeout=5)


if __name__ == "__main__":
    main()
