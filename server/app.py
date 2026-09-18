"""Read-only sync endpoints for the package server (SPEC.md §4.1).

Build with :func:`create_app` (used by tests against a temp store) or run the
module-level ``app`` under uvicorn:

    uvicorn server.app:app --host 0.0.0.0 --port 8001

Serving is plain HTTP over the LAN. Auth is reserved: the ``X-Device-Token``
header is accepted and ignored (SPEC.md §4.1).
"""

import json
import os
import re

from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, Response

from server import DEFAULT_STORE

DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _is_safe_name(value, pattern):
    return bool(value) and ".." not in value and pattern.match(value) is not None


def create_app(store_dir=None):
    """Build a FastAPI app serving packages/records from ``store_dir``.

    Layout: ``<store>/packages/<package_id>.zip`` and
    ``<store>/devices/<device_id>.json``, both written by ``server.publish``.
    """
    store_dir = os.fspath(store_dir or DEFAULT_STORE)
    devices_dir = os.path.join(store_dir, "devices")
    packages_dir = os.path.join(store_dir, "packages")

    app = FastAPI(title="r36s-disp sync server", version="1")

    @app.get("/api/v1/devices/{device_id}/latest")
    def latest(device_id: str, x_device_token: Optional[str] = Header(default=None)):
        if not _is_safe_name(device_id, DEVICE_ID_RE):
            raise HTTPException(status_code=404, detail="unknown device")
        path = os.path.join(devices_dir, device_id + ".json")
        if not os.path.isfile(path):
            return Response(status_code=204)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            raise HTTPException(status_code=500, detail="corrupt device record")

    @app.get("/api/v1/packages/{filename}.zip")
    def package(filename: str):
        if not _is_safe_name(filename, PACKAGE_NAME_RE):
            raise HTTPException(status_code=404, detail="not found")
        path = os.path.join(packages_dir, filename + ".zip")
        if not os.path.isfile(path):
            raise HTTPException(status_code=404, detail="not found")
        return FileResponse(path, media_type="application/zip",
                            filename=filename + ".zip")

    return app


app = create_app()
