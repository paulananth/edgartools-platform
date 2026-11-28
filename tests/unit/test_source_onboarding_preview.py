from __future__ import annotations

from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from edgar_warehouse.source_onboarding_preview import create_server


def test_source_onboarding_guide_is_local_read_only_and_escapes_source_name():
    server = create_server(source_name='sec <company> & "sample"')
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert server.server_address[0] == "127.0.0.1"
        url = f"http://127.0.0.1:{server.server_port}/"
        with urlopen(url) as response:
            page = response.read().decode("utf-8")
            assert response.headers["Content-Security-Policy"].find("script-src 'none'") >= 0
        assert '<h2 class="source-name" id="source-title">sec &lt;company&gt; &amp; &quot;sample&quot;</h2>' in page
        assert "Guide only · no run state" in page
        assert "edgar-warehouse rules try --family &lt;family&gt;" in page
        assert "sources/&lt;source&gt;/quality.yaml" in page
        assert "Show the full rule" in page

        request = Request(url, data=b"", method="POST")
        try:
            urlopen(request)
        except HTTPError as error:
            assert error.code == 405
            assert b"no onboarding actions are available" in error.read()
        else:
            raise AssertionError("The read-only onboarding guide accepted a POST request.")

        try:
            urlopen(url + "unknown")
        except HTTPError as error:
            assert error.code == 404
        else:
            raise AssertionError("The onboarding guide exposed an unknown route.")
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
