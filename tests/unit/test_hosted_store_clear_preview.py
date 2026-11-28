from __future__ import annotations

import json
import re
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from edgar_warehouse.hosted_store_clear_preview import create_server
from edgar_warehouse.hosted_store_clear_progress import STEPS, record_unit, start_run


def test_hosted_clear_preview_streams_run_progress_without_cleanup_actions(tmp_path):
    run_id = start_run(stores_folder=tmp_path)
    server = create_server(run_id=run_id, stores_folder=tmp_path)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert server.server_address[0] == "127.0.0.1"
        url = f"http://127.0.0.1:{server.server_port}/"
        with urlopen(url) as response:
            page = response.read().decode("utf-8")
        assert f"Run {run_id[:8]}" in page
        assert "Monitor only. This page cannot start cleanup." in page
        assert page.count("<progress ") == len(STEPS)
        assert '<meta name="robots" content="noindex">' in page
        assert not re.search(r"<button\b|<form\b", page, re.IGNORECASE)

        with urlopen(url + "progress") as response:
            before = json.loads(response.read())
        assert before["steps"]["reset"]["completed"] == 0

        record_unit(run_id, "reset", "mdm", "running", tmp_path)
        record_unit(run_id, "reset", "mdm", "completed", tmp_path)
        with urlopen(url + "progress") as response:
            after = json.loads(response.read())
        assert after["steps"]["reset"]["completed"] == 1
        assert after["steps"]["reset"]["state"] == "running"

        request = Request(url + "action", data=b"", method="POST")
        try:
            urlopen(request)
        except HTTPError as error:
            assert error.code == 405
            assert b"no cleanup actions are available" in error.read()
        else:
            raise AssertionError("The read-only preview accepted a POST request.")
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
