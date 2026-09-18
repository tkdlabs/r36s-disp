"""Best-effort WiFi recovery for the R36S launcher (SPEC.md §5.2, #29).

Stdlib only, Python 3.7+ (the device ships 3.7.5). The RTL8188EUS USB dongle
(``r8188eu``) is flaky on the RK3326: it can drop off the USB bus
(``device descriptor read/64, error -71``) and needs a re-enumeration, and
NetworkManager / EmulationStation can leave networking or the WiFi radio off.
``rfkill`` is NOT installed on ArkOS, so recovery uses ``nmcli`` and the same
USB power-cycle as ``../r36s/scripts/remote-setup.sh``.

:func:`plan_actions` and :func:`parse_device_state` are pure and unit-tested
without a device; :func:`recover` executes the plan best-effort and never
raises.

CLI:

    python -m app.netrecover [--wait SECONDS]

Exits 0 when ``wlan0`` is connected at the end, 1 otherwise; callers ignore it.
"""

import argparse
import glob
import os
import subprocess
import sys
import time

WLAN = "wlan0"
MODULE = "r8188eu"
SYS_NET = "/sys/class/net"
USB_GLOB = "/sys/bus/usb/devices/usb*/authorized"
DEFAULT_WAIT = 15

NM_ON = "networking-on"
RADIO_ON = "radio-on"
RELOAD = "reload-driver"
CONNECT = "connect"
WAIT = "wait"


def plan_actions(interface_present, connected):
    """Return the ordered recovery actions for the probed state (pure).

    A missing ``wlan0`` means the dongle fell off the USB bus, so it must be
    reloaded and re-enumerated; otherwise it is enough to ensure the radio is
    on and (re)connect the saved profile.
    """
    if not interface_present:
        return [NM_ON, RADIO_ON, RELOAD, WAIT]
    if connected:
        return [NM_ON, RADIO_ON]
    return [NM_ON, RADIO_ON, CONNECT, WAIT]


def parse_device_state(nmcli_output):
    """True if ``wlan0`` is connected per ``nmcli -t -f DEVICE,STATE device``."""
    for line in nmcli_output.splitlines():
        fields = line.strip().split(":")
        if len(fields) >= 2 and fields[0] == WLAN:
            return fields[1] == "connected"
    return False


def _default_runner(cmd):
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        out, _ = proc.communicate()
        return proc.returncode, out.decode("utf-8", "replace")
    except OSError as exc:
        return 127, str(exc)


def _run(runner, cmd):
    try:
        return runner(cmd)
    except Exception as exc:  # recovery must never raise
        return 1, str(exc)


def _connected(runner):
    rc, out = _run(runner, ["nmcli", "-t", "-f", "DEVICE,STATE", "device"])
    return rc == 0 and parse_device_state(out)


def _interface_present():
    return os.path.exists(os.path.join(SYS_NET, WLAN))


def _write(path, value):
    try:
        with open(path, "w") as fh:
            fh.write(value)
    except OSError:
        pass


def _reload_usb(runner, sleeper):
    """Reload ``r8188eu`` and power-cycle the USB root hubs (needs root)."""
    _run(runner, ["modprobe", "-r", MODULE])
    for path in sorted(glob.glob(USB_GLOB)):
        _write(path, "0")
    sleeper(3.0)
    for path in sorted(glob.glob(USB_GLOB)):
        _write(path, "1")
    sleeper(3.0)
    _run(runner, ["modprobe", MODULE])
    sleeper(3.0)


def _wait_for_link(runner, sleeper, wait):
    deadline = time.monotonic() + max(0.0, wait)
    while True:
        if _connected(runner):
            return True
        if time.monotonic() >= deadline:
            return False
        sleeper(1.0)


def recover(wait=DEFAULT_WAIT, runner=None, sleeper=time.sleep,
            interface_present=None):
    """Run the recovery plan best-effort; return whether wlan0 is connected."""
    runner = runner or _default_runner
    interface_present = interface_present or _interface_present
    actions = plan_actions(interface_present(), _connected(runner))
    for action in actions:
        if action == NM_ON:
            _run(runner, ["nmcli", "networking", "on"])
        elif action == RADIO_ON:
            _run(runner, ["nmcli", "radio", "wifi", "on"])
        elif action == RELOAD:
            _reload_usb(runner, sleeper)
        elif action == CONNECT:
            _run(runner, ["nmcli", "device", "connect", WLAN])
        elif action == WAIT and _wait_for_link(runner, sleeper, wait):
            return True
    return _connected(runner)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m app.netrecover",
        description="Best-effort R36S WiFi/USB radio recovery.",
    )
    parser.add_argument("--wait", type=float, default=DEFAULT_WAIT,
                        help="seconds to wait for wlan0 (default: %(default)s)")
    args = parser.parse_args(argv)
    return 0 if recover(args.wait) else 1


if __name__ == "__main__":
    sys.exit(main())
