import pytest

from gateway.errors import AccountLocked, Forbidden, InvalidCredentials, SessionExpired, WeakPassword
from gateway.service import AuthService


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make():
    clock = Clock()
    svc = AuthService(clock)
    svc.register("ada", "correct-horse-9")
    svc.register("root", "another-long-pass-1", role="admin")
    return svc, clock


def test_weak_passwords():
    svc, _ = make()
    with pytest.raises(WeakPassword):
        svc.register("x", "short1")
    with pytest.raises(WeakPassword):
        svc.register("x", "nodigitsatall-here")


def test_login_and_logout():
    svc, _ = make()
    token = svc.login("ada", "correct-horse-9")
    svc.logout(token)
    with pytest.raises(SessionExpired):
        svc.sessions.validate(token)


def test_wrong_password():
    svc, _ = make()
    with pytest.raises(InvalidCredentials):
        svc.login("ada", "nope")


def test_lockout_eventually_happens():
    svc, _ = make()
    with pytest.raises(AccountLocked):
        for _ in range(10):
            try:
                svc.login("ada", "bad")
            except InvalidCredentials:
                pass


def test_session_expires_when_idle():
    svc, clock = make()
    token = svc.login("ada", "correct-horse-9")
    clock.now += 31 * 60
    with pytest.raises(SessionExpired):
        svc.sessions.validate(token)


def test_admin_guard():
    svc, _ = make()
    member = svc.login("ada", "correct-horse-9")
    with pytest.raises(Forbidden):
        svc.admin_action(member, "purge")
    admin = svc.login("root", "another-long-pass-1")
    assert svc.admin_action(admin, "purge") == "purge done"
