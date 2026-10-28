"""Link reviewed result copies through the current Jupyter file server."""
from __future__ import annotations

from html import escape
import os
from pathlib import Path
from urllib.parse import quote, urlsplit


def result_links(exports: dict, servers: list[dict] | None = None) -> dict[str, str]:
    """Return same-origin file URLs, or no URLs when no unambiguous server serves them."""
    if servers is None:
        from jupyter_server.serverapp import list_running_servers
        servers = list(list_running_servers())
    index, archive = (Path(exports[key]).resolve() for key in ("index_path", "zip_path"))
    candidates = {}
    for server in servers:
        if not server.get("root_dir"):
            continue
        root = Path(server["root_dir"]).resolve()
        base = server.get("base_url", "/")
        parsed = urlsplit(base)
        if (not base.startswith("/") or base.startswith("//") or parsed.netloc
                or parsed.query or parsed.fragment or "\\" in base):
            continue
        if index.is_relative_to(root) and archive.is_relative_to(root):
            candidates[(root, base)] = server
    prefix = os.environ.get("JUPYTERHUB_SERVICE_PREFIX")
    parent = os.environ.get("JPY_PARENT_PID", str(os.getppid()))
    preferred = {key: server for key, server in candidates.items()
                 if str(server.get("pid")) == parent or (prefix and key[1] == prefix)}
    if preferred:
        candidates = preferred
    if len(candidates) != 1:
        return {}
    root, base = next(iter(candidates))
    file_prefix = base.rstrip("/") + "/files/"
    return {
        "figures": file_prefix + quote(index.relative_to(root).as_posix(), safe="/"),
        "zip": file_prefix + quote(archive.relative_to(root).as_posix(), safe="/") + "?download=1",
    }


def display_results(exports: dict) -> None:
    """Show download actions in Jupyter, with usable paths for command-line execution."""
    from IPython.display import HTML, display
    if exports.get("artificial_data"):
        display(HTML("<p><strong>Artificial demonstration data — not empirical study results.</strong></p>"))
    links = result_links(exports)
    if links:
        style = "display:inline-block;padding:10px 16px;margin:4px;border:1px solid #267b83;border-radius:6px;"
        display(HTML(
            '<p><strong>Results are ready</strong></p>'
            f'<a style="{style}" href="{escape(links["figures"])}" target="_blank" rel="noopener">View nine figures</a>'
            f'<a style="{style}" href="{escape(links["zip"])}" download>Download figures and aggregates (ZIP)</a>'
            '<p>The ZIP contains nine figures in PNG/PDF formats, the plotting aggregates, and ten result tables.</p>'
        ))
    else:
        print("Figure preview:", exports["index_path"])
        print("Results ZIP:", exports["zip_path"])
    print("Download copies:", exports["directory"])
