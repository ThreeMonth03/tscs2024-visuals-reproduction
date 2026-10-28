"""Download links must work under JupyterHub prefixes without exposing credentials."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from helpers.notebook_display import result_links


class ResultLinkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        directory = self.root / "notebooks/downloads/圖表 01"
        self.exports = {"index_path": directory / "index.html", "zip_path": directory / "results.zip"}

    def test_jupyterhub_urls_use_server_root_prefix_and_no_token(self):
        server = {"root_dir": str(self.root), "base_url": "/user/test-session/", "token": "never-embed"}
        links = result_links(self.exports, [server])
        self.assertEqual(links["figures"], "/user/test-session/files/notebooks/downloads/%E5%9C%96%E8%A1%A8%2001/index.html")
        self.assertTrue(links["zip"].endswith("/results.zip?download=1"))
        self.assertNotIn("never-embed", str(links))

    def test_notebook_directory_as_server_root(self):
        links = result_links(self.exports, [{"root_dir": str(self.root / "notebooks"), "base_url": "/"}])
        self.assertTrue(links["figures"].startswith("/files/downloads/"))

    def test_no_serving_server_returns_local_path_fallback(self):
        self.assertEqual(result_links(self.exports, []), {})
        self.assertEqual(result_links(self.exports, [{"root_dir": str(self.root / "elsewhere")}]), {})

    def test_ambiguous_servers_do_not_guess_an_endpoint(self):
        servers = [{"root_dir": str(self.root), "base_url": base, "pid": pid}
                   for pid, base in ((111, "/one/"), (222, "/two/"))]
        with patch.dict(os.environ, {"JPY_PARENT_PID": "333", "JUPYTERHUB_SERVICE_PREFIX": ""}):
            self.assertEqual(result_links(self.exports, servers), {})
        with patch.dict(os.environ, {"JPY_PARENT_PID": "222", "JUPYTERHUB_SERVICE_PREFIX": ""}):
            self.assertTrue(result_links(self.exports, servers)["zip"].startswith("/two/files/"))

    def test_external_or_malformed_base_url_is_rejected(self):
        for base in ("https://other.example/", "//other.example/", "/?token=secret", "/#fragment", "/\\other"):
            with self.subTest(base=base):
                self.assertEqual(result_links(self.exports, [{"root_dir": str(self.root), "base_url": base}]), {})


if __name__ == "__main__":
    unittest.main()
