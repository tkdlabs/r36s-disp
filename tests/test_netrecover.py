import pytest

from app.netrecover import (
    CONNECT,
    NM_ON,
    RADIO_ON,
    RELOAD,
    WAIT,
    parse_device_state,
    plan_actions,
    recover,
)


class FakeRunner:
    def __init__(self, connected=False, connect_after=1):
        self.calls = []
        self.connected = connected
        self._connect_after = connect_after
        self._connect_calls = 0

    def __call__(self, cmd):
        self.calls.append(cmd)
        if cmd[:3] == ["nmcli", "-t", "-f"]:
            state = "connected" if self.connected else "disconnected"
            return 0, "wlan0:%s\n" % state
        if cmd[:3] == ["nmcli", "device", "connect"]:
            self._connect_calls += 1
            if self._connect_calls >= self._connect_after:
                self.connected = True
        return 0, ""


def commands(runner):
    return [tuple(cmd) for cmd in runner.calls]


def test_plan_absent_interface_reloads_driver():
    actions = plan_actions(interface_present=False, connected=False)
    assert RELOAD in actions
    assert CONNECT not in actions


def test_plan_present_and_connected_only_ensures_radio():
    assert plan_actions(interface_present=True, connected=True) == [NM_ON, RADIO_ON]


def test_plan_present_disconnected_reconnects():
    actions = plan_actions(interface_present=True, connected=False)
    assert CONNECT in actions and WAIT in actions


@pytest.mark.parametrize("output,expected", [
    ("wlan0:connected\n", True),
    ("lo:connected (externally)\nwlan0:disconnected\n", False),
    ("eth0:connected\n", False),
    ("", False),
    ("garbage", False),
])
def test_parse_device_state(output, expected):
    assert parse_device_state(output) is expected


def test_recover_connected_does_not_touch_usb():
    runner = FakeRunner(connected=True)
    assert recover(runner=runner, sleeper=lambda _s: None,
                   interface_present=lambda: True) is True
    assert ("nmcli", "networking", "on") in commands(runner)
    assert ("nmcli", "radio", "wifi", "on") in commands(runner)
    assert ("modprobe", "-r", "r8188eu") not in commands(runner)
    assert ("nmcli", "device", "connect") not in commands(runner)


def test_recover_disconnected_connects_and_waits():
    runner = FakeRunner(connected=False, connect_after=1)
    assert recover(runner=runner, sleeper=lambda _s: None,
                   interface_present=lambda: True) is True
    assert ("nmcli", "device", "connect", "wlan0") in commands(runner)


def test_recover_absent_interface_reloads_driver():
    runner = FakeRunner(connected=False)
    result = recover(runner=runner, sleeper=lambda _s: None, wait=0,
                     interface_present=lambda: False)
    assert result is False
    assert ("modprobe", "r8188eu") in commands(runner)
    assert ("nmcli", "device", "connect") not in commands(runner)


def test_recover_never_raises_when_tools_fail():
    class Boom:
        def __call__(self, cmd):
            raise RuntimeError("boom")

    assert recover(runner=Boom(), sleeper=lambda _s: None, wait=0,
                   interface_present=lambda: True) is False
