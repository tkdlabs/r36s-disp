import contextlib
import hashlib
import json
import os
import socket
import threading
import time
import zipfile

import pytest
import uvicorn

from app.current import packages_dir, read_current, resolve_current, write_current
from app.main import (
    _sync_summary,
    make_reload_callback,
    make_sync_callback,
)
from app.sync import main, sync
from server.app import create_app
from server.publish import publish_package

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTPKG = os.path.join(ROOT, "testpackages")


@contextlib.contextmanager
def running_server(store):
    app = create_app(store)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]

    config = uvicorn.Config(app, log_level="error", lifespan="off")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]},
                              daemon=True)
    thread.start()
    limit = time.time() + 10
    while not server.started:
        if time.time() > limit:
            raise RuntimeError("test server did not start")
        time.sleep(0.01)
    try:
        yield "http://127.0.0.1:%d" % port
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()


@pytest.fixture
def env(tmp_path):
    store = str(tmp_path / "store")
    with running_server(store) as url:
        yield url, store


def publish(store, package="full", device="dev-1", retention_days=7):
    return publish_package(
        os.path.join(TESTPKG, package),
        device,
        store_dir=store,
        retention_days=retention_days,
    )


def write_config(tmp_path, server_url, device_id="dev-1", max_retention_days=7):
    path = str(tmp_path / "config.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({
            "server_url": server_url,
            "device_id": device_id,
            "max_retention_days": max_retention_days,
        }, fh)
    return path


def fake_install(data_dir, package_id, date):
    path = os.path.join(packages_dir(data_dir), package_id)
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump({"spec": 1, "package": {"id": package_id, "date": date},
                   "root": "a", "screens": {"a": {"type": "text", "body": "x"}}}, fh)
    return path


def write_record(store, record):
    devices = os.path.join(store, "devices")
    os.makedirs(devices, exist_ok=True)
    with open(os.path.join(devices, "dev-1.json"), "w", encoding="utf-8") as fh:
        json.dump(record, fh)


def zip_dir(src, dst):
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _dirs, files in os.walk(src):
            for name in files:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, src).replace(os.sep, "/")
                zf.write(full, rel)


def store_zip(store, package_id, zip_path, date="2026-09-03"):
    with open(zip_path, "rb") as fh:
        data = fh.read()
    record = {
        "package_id": package_id,
        "date": date,
        "url": "/api/v1/packages/%s.zip" % package_id,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "retention_days": 7,
    }
    write_record(store, record)
    return record


def test_happy_path_installs(tmp_path, env):
    url, store = env
    record = publish(store, "full")
    config = write_config(tmp_path, url)
    data_dir = str(tmp_path / "data")

    state = sync(config, data_dir)

    assert state["status"] == "installed"
    assert state["package_id"] == record["package_id"]
    assert "error" not in state
    assert read_current(data_dir) == record["package_id"]
    installed = resolve_current(data_dir)
    assert installed is not None
    assert os.path.isfile(os.path.join(installed, "manifest.json"))
    with open(os.path.join(data_dir, "state.json"), encoding="utf-8") as fh:
        assert json.load(fh)["status"] == "installed"
    assert os.listdir(os.path.join(data_dir, "incoming")) == []


def test_default_data_dir_is_next_to_config(tmp_path, env):
    url, _store = env
    config = write_config(tmp_path, url)

    state = sync(config)

    assert state["status"] == "no-package"
    assert os.path.isfile(os.path.join(str(tmp_path), "data", "state.json"))


def test_no_package_is_nonfatal(tmp_path, env):
    url, _store = env
    state = sync(write_config(tmp_path, url), str(tmp_path / "data"))
    assert state["status"] == "no-package"
    assert state["package_id"] is None


def test_idempotent_second_sync_is_noop(tmp_path, env):
    url, store = env
    publish(store, "full")
    config = write_config(tmp_path, url)
    data_dir = str(tmp_path / "data")

    first = sync(config, data_dir)
    second = sync(config, data_dir)

    assert first["status"] == "installed"
    assert second["status"] == "up-to-date"
    assert second["package_id"] == first["package_id"]
    assert len(os.listdir(packages_dir(data_dir))) == 1


def test_sha256_mismatch_keeps_previous(tmp_path, env):
    url, store = env
    first = publish(store, "full")
    config = write_config(tmp_path, url)
    data_dir = str(tmp_path / "data")
    assert sync(config, data_dir)["status"] == "installed"

    second = publish(store, "minimal")
    with open(os.path.join(store, "devices", "dev-1.json"), encoding="utf-8") as fh:
        record = json.load(fh)
    record["sha256"] = "0" * 64
    write_record(store, record)

    state = sync(config, data_dir)

    assert state["status"] == "error"
    assert "sha256" in state["error"]
    assert read_current(data_dir) == first["package_id"]
    assert not os.path.isdir(os.path.join(packages_dir(data_dir), second["package_id"]))


def test_invalid_manifest_keeps_previous(tmp_path, env):
    url, store = env
    first = publish(store, "full")
    config = write_config(tmp_path, url)
    data_dir = str(tmp_path / "data")
    assert sync(config, data_dir)["status"] == "installed"

    broken = "broken-2026-09-03-0001"
    os.makedirs(os.path.join(store, "packages"), exist_ok=True)
    zip_path = os.path.join(store, "packages", broken + ".zip")
    zip_dir(os.path.join(TESTPKG, "invalid", "spec-2"), zip_path)
    store_zip(store, broken, zip_path)

    state = sync(config, data_dir)

    assert state["status"] == "error"
    assert "invalid package" in state["error"]
    assert read_current(data_dir) == first["package_id"]
    assert not os.path.isdir(os.path.join(packages_dir(data_dir), broken))


def test_intra_day_revision_installs(tmp_path, env):
    url, store = env
    first = publish(store, "full")
    config = write_config(tmp_path, url)
    data_dir = str(tmp_path / "data")
    assert sync(config, data_dir)["status"] == "installed"

    second = publish(store, "full")
    assert second["package_id"] != first["package_id"]
    assert second["date"] == first["date"]

    state = sync(config, data_dir)

    assert state["status"] == "installed"
    assert read_current(data_dir) == second["package_id"]
    assert os.path.isdir(os.path.join(packages_dir(data_dir), first["package_id"]))


def test_retention_prunes_old_keeps_window(tmp_path, env):
    url, store = env
    record = publish(store, "full")
    config = write_config(tmp_path, url)
    data_dir = str(tmp_path / "data")
    fake_install(data_dir, "stale-2026-01-01-0001", "2026-01-01")
    fake_install(data_dir, "keep-2026-09-01-0001", "2026-09-01")

    state = sync(config, data_dir)

    assert state["status"] == "installed"
    assert not os.path.isdir(
        os.path.join(packages_dir(data_dir), "stale-2026-01-01-0001"))
    assert os.path.isdir(
        os.path.join(packages_dir(data_dir), "keep-2026-09-01-0001"))
    assert os.path.isdir(
        os.path.join(packages_dir(data_dir), record["package_id"]))


def test_device_cap_overrides_server_retention(tmp_path, env):
    url, store = env
    record = publish(store, "full", retention_days=365)
    config = write_config(tmp_path, url, max_retention_days=7)
    data_dir = str(tmp_path / "data")
    fake_install(data_dir, "mid-2026-03-01-0001", "2026-03-01")

    state = sync(config, data_dir)

    assert state["status"] == "installed"
    assert not os.path.isdir(
        os.path.join(packages_dir(data_dir), "mid-2026-03-01-0001"))
    assert os.path.isdir(
        os.path.join(packages_dir(data_dir), record["package_id"]))


def test_never_prunes_current(tmp_path, env):
    url, store = env
    config = write_config(tmp_path, url)
    data_dir = str(tmp_path / "data")
    current_id = "old-2026-07-01-0001"
    fake_install(data_dir, current_id, "2026-07-01")
    write_current(data_dir, current_id)
    write_record(store, {
        "package_id": current_id,
        "date": "2026-08-01",
        "url": "/api/v1/packages/%s.zip" % current_id,
        "sha256": "0" * 64,
        "size": 1,
        "retention_days": 7,
    })

    state = sync(config, data_dir)

    assert state["status"] == "up-to-date"
    assert os.path.isdir(os.path.join(packages_dir(data_dir), current_id))


def test_unsafe_path_is_rejected(tmp_path, env):
    url, store = env
    package_id = "evil-2026-09-03-0001"
    os.makedirs(os.path.join(store, "packages"), exist_ok=True)
    zip_path = os.path.join(store, "packages", package_id + ".zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("manifest.json", json.dumps({
            "spec": 1, "root": "a",
            "screens": {"a": {"type": "text", "body": "hi"}}}))
        zf.writestr("../evil.txt", "pwned")
    store_zip(store, package_id, zip_path)
    data_dir = str(tmp_path / "data")

    state = sync(write_config(tmp_path, url), data_dir)

    assert state["status"] == "error"
    assert "unsafe path" in state["error"]
    assert not os.path.exists(os.path.join(data_dir, "incoming", "evil.txt"))


def test_unreachable_server_is_nonfatal(tmp_path):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    config = write_config(tmp_path, "http://127.0.0.1:%d" % port)

    state = sync(config, str(tmp_path / "data"), timeout=2)

    assert state["status"] == "error"
    assert state["error"]


def test_missing_config_is_nonfatal(tmp_path):
    state = sync(str(tmp_path / "missing.json"), str(tmp_path / "data"))
    assert state["status"] == "error"


def test_cli_entry_point(tmp_path, env):
    url, store = env
    publish(store, "full")
    config = write_config(tmp_path, url)
    data_dir = str(tmp_path / "data")

    rc = main([config, "--data-dir", data_dir])

    assert rc == 0
    assert read_current(data_dir) is not None


def test_sync_summary_mappings():
    assert _sync_summary({"status": "installed",
                          "package_id": "x-2026-09-03-0001"}) == \
        "synced x-2026-09-03-0001"
    assert _sync_summary({"status": "up-to-date"}) == "already up to date"
    assert _sync_summary({"status": "no-package"}) == "nothing to sync"
    assert _sync_summary({"status": "error", "error": "boom"}) == \
        "sync failed: boom"
    assert _sync_summary({"status": "error"}) == "sync failed: unknown error"


def test_player_sync_callback_installs_and_summarizes(tmp_path, env):
    url, store = env
    record = publish(store, "full")
    config = write_config(tmp_path, url)
    data_dir = str(tmp_path / "data")

    callback = make_sync_callback(config, data_dir)
    assert callback is not None
    summary = callback()

    assert summary == "synced %s" % record["package_id"]
    assert read_current(data_dir) == record["package_id"]


def test_player_sync_callback_second_call_is_up_to_date(tmp_path, env):
    url, store = env
    publish(store, "full")
    config = write_config(tmp_path, url)
    data_dir = str(tmp_path / "data")

    callback = make_sync_callback(config, data_dir)

    assert "synced" in callback()
    assert callback() == "already up to date"


def test_player_sync_callback_no_package(tmp_path, env):
    url, _store = env
    data_dir = str(tmp_path / "data")
    callback = make_sync_callback(write_config(tmp_path, url), data_dir)

    assert callback() == "nothing to sync"


def test_player_sync_callback_error_summary(tmp_path, env):
    url, store = env
    publish(store, "full")
    config = write_config(tmp_path, url)
    data_dir = str(tmp_path / "data")
    callback = make_sync_callback(config, data_dir)
    assert "synced" in callback()

    second = publish(store, "minimal")
    assert second["package_id"]
    with open(os.path.join(store, "devices", "dev-1.json"),
              encoding="utf-8") as fh:
        record = json.load(fh)
    record["sha256"] = "0" * 64
    write_record(store, record)

    summary = callback()
    assert summary.startswith("sync failed: sha256 mismatch")
    assert read_current(data_dir) != second["package_id"]


def test_reload_callback_reflects_installed_edition(tmp_path, env):
    url, store = env
    record = publish(store, "full")
    config = write_config(tmp_path, url)
    data_dir = str(tmp_path / "data")

    reload = make_reload_callback(data_dir)
    assert reload().package_id == "builtin"

    make_sync_callback(config, data_dir)()
    assert record["package_id"]
    assert reload().source == resolve_current(data_dir)


def test_player_sync_callback_without_config_is_none(tmp_path):
    assert make_sync_callback(str(tmp_path / "missing.json")) is None
