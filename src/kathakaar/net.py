"""Small cross-platform HTTP helpers for source and media ingestion."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, cast
from urllib.request import Request, urlopen


def download_bytes(
    url: str,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 30.0,
) -> bytes:
    request_headers = headers or {}
    curl = shutil.which("curl.exe") if os.name == "nt" else None
    if os.name == "nt" and curl is None:
        system_curl = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "curl.exe"
        curl = str(system_curl) if system_curl.exists() else None
    if curl:
        command = [
            curl,
            "--fail",
            "--silent",
            "--show-error",
            "--location",
            "--max-time",
            str(max(1, int(timeout_seconds))),
        ]
        command.append("--ssl-no-revoke")
        for key, value in request_headers.items():
            command.extend(["--header", f"{key}: {value}"])
        command.append(url)
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
        )
        return result.stdout

    request = Request(url, headers=request_headers)
    with urlopen(request, timeout=timeout_seconds) as response:
        return cast(bytes, response.read())


def download_json(
    url: str,
    headers: dict[str, str] | None = None,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    payload = json.loads(download_bytes(url, headers, timeout_seconds).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("HTTP endpoint did not return a JSON object")
    return cast(dict[str, Any], payload)
