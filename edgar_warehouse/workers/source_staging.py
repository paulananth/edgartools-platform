"""Publishable artifact identities over a private local staging directory.

Workers and verifiers read exactly the bytes that will be renamed into place;
receipts use the final root so they remain usable after atomic publication.
"""

from pathlib import Path
from urllib.parse import unquote, urlparse
from edgar_warehouse.bookkeeping.clean.artifacts import Artifacts


class StagedArtifacts(Artifacts):
    def __init__(self, final_root: Path, staging_root: Path):
        super().__init__()
        self._physical = Artifacts()
        self.final_root = final_root.resolve()
        self.staging_root = staging_root.resolve()

    def _local(self, uri):
        parsed = urlparse(uri)
        if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
            raise ValueError("Staged artifact must name a local member")
        path = Path(unquote(parsed.path))
        # Resolve before checking containment, refusing traversal and symlinks.
        path = path.resolve()
        if not path.is_relative_to(self.final_root):
            raise ValueError("Staged artifact escapes its publication root")
        relative = path.relative_to(self.final_root)
        staged = (self.staging_root / relative).resolve()
        if not staged.is_relative_to(self.staging_root):
            raise ValueError("Staged artifact escapes its staging root")
        return staged.as_uri()

    def read(self, uri, *, max_bytes=None):
        return self._physical.read(self._local(uri), max_bytes=max_bytes)

    def put_bytes(self, uri, data):
        receipt = self._physical.put_bytes(self._local(uri), data)
        return {**receipt, "uri": uri}
