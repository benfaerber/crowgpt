"""Run with CADDY_BIN pointing to the deployed Caddy binary (no production writes)."""
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

import pytest
from werkzeug.serving import make_server
from fieldserver.core.proxy import CaddyCloudflareProxy


@pytest.mark.skipif(not os.environ.get("CADDY_BIN"), reason="requires the deployed Caddy binary")
def test_caddy_overwrites_client_supplied_forwarding_headers(tmp_path):
    def echo(environ, start):
        start("200 OK", [("Content-Type", "application/json")])
        return [json.dumps({"ip": environ["REMOTE_ADDR"]}).encode()]
    backend = make_server("127.0.0.1", 0, CaddyCloudflareProxy(echo))
    thread = threading.Thread(target=backend.serve_forever, daemon=True)
    thread.start()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    deployed = (Path(__file__).parents[1] / "deploy" / "Caddyfile").read_text()
    proxy = deployed[deployed.index("\treverse_proxy"):].replace("127.0.0.1:5100", f"127.0.0.1:{backend.server_port}")
    config = tmp_path / "Caddyfile"
    config.write_text("{\n admin off\n}\n" + f"http://127.0.0.1:{port} {{\n" + proxy)
    with (tmp_path / "caddy.log").open("w+") as log:
        process = subprocess.Popen([os.environ["CADDY_BIN"], "run", "--config", str(config), "--adapter", "caddyfile"],
                                   stdout=log, stderr=log)
        try:
            request = Request(f"http://127.0.0.1:{port}/", headers={
                "X-Forwarded-For": "173.245.48.1", "CF-Connecting-IP": "203.0.113.88"})
            for _ in range(100):
                try:
                    with urlopen(request, timeout=1) as answer:
                        assert json.load(answer)["ip"] == "127.0.0.1"
                    break
                except URLError:
                    time.sleep(.05)
            else:
                pytest.fail("Caddy did not start")
        finally:
            process.terminate()
            process.wait(timeout=5)
            backend.shutdown()
            backend.server_close()
            thread.join(timeout=5)
