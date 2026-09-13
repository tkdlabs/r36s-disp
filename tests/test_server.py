import hashlib
import os

import pytest

from fastapi.testclient import TestClient

from server.app import create_app
from server.publish import PublishError, publish_package

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTPKG = os.path.join(ROOT, "testpackages")


@pytest.fixture
def store(tmp_path):
    return str(tmp_path / "store")


def _publish(store, package="full", device="dev-1", retention_days=None):
    return publish_package(
        os.path.join(TESTPKG, package),
        device,
        store_dir=store,
        retention_days=retention_days,
    )


def test_latest_and_download_round_trip(store):
    record = _publish(store, "full", "dev-1", retention_days=7)
    client = TestClient(create_app(store))

    resp = client.get("/api/v1/devices/dev-1/latest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["package_id"] == record["package_id"]
    assert body["date"] == "2026-09-03"
    assert body["url"] == record["url"]
    assert body["sha256"] == record["sha256"]
    assert body["size"] == record["size"]
    assert body["retention_days"] == 7

    download = client.get(body["url"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    data = download.content
    assert len(data) == record["size"]
    assert hashlib.sha256(data).hexdigest() == record["sha256"]

    served = os.path.join(store, "packages", record["package_id"] + ".zip")
    with open(served, "rb") as fh:
        assert fh.read() == data


def test_unknown_device_is_204(store):
    client = TestClient(create_app(store))
    assert client.get("/api/v1/devices/nobody/latest").status_code == 204


def test_device_token_header_accepted(store):
    _publish(store)
    client = TestClient(create_app(store))
    resp = client.get("/api/v1/devices/dev-1/latest",
                      headers={"X-Device-Token": "reserved"})
    assert resp.status_code == 200


def test_invalid_package_is_refused_without_touching_store(store):
    with pytest.raises(PublishError):
        _publish(store, os.path.join("invalid", "spec-2"))
    assert not os.path.exists(os.path.join(store, "packages"))
    assert not os.path.exists(os.path.join(store, "devices"))


def test_republish_same_content_mints_new_package_id(store):
    first = _publish(store, "full", "dev-1")
    second = _publish(store, "full", "dev-1")
    assert first["package_id"] != second["package_id"]
    assert second["package_id"].startswith("full-2026-09-03-")


def test_publish_to_multiple_devices_shares_one_package(store):
    record = _publish(store, "minimal", ["dev-1", "dev-2"])
    client = TestClient(create_app(store))
    for device in ("dev-1", "dev-2"):
        body = client.get("/api/v1/devices/%s/latest" % device).json()
        assert body["package_id"] == record["package_id"]
    zips = [n for n in os.listdir(os.path.join(store, "packages"))
            if n.endswith(".zip")]
    assert zips == [record["package_id"] + ".zip"]


def test_missing_package_is_404(store):
    client = TestClient(create_app(store))
    assert client.get("/api/v1/packages/does-not-exist.zip").status_code == 404
