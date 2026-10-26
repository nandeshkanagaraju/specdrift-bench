from dataclasses import dataclass
from typing import Callable

from gateway import passwords
from gateway.errors import (
    AccountLocked,
    Forbidden,
    InvalidCredentials,
    UnknownUser,
)
from gateway.sessions import SessionStore

MAX_FAILURES = 5
LOCK_SECONDS = 15 * 60


@dataclass
class User:
    name: str
    salt: bytes
    digest: bytes
    role: str = "member"
    failures: int = 0
    locked_until: float = 0.0


class AuthService:
    def __init__(self, clock: Callable[[], float]) -> None:
        self.clock = clock
        self.users: dict[str, User] = {}
        self.sessions = SessionStore(clock)
        self.audit: list[str] = []

    def register(self, name: str, password: str, role: str = "member") -> None:
        passwords.validate(password)
        salt, digest = passwords.hash_password(password)
        self.users[name] = User(name, salt, digest, role)

    def login(self, name: str, password: str) -> str:
        user = self.users.get(name)
        if user is None:
            self.audit.append(f"failed login: {name}")
            raise UnknownUser(name)
        if self.clock() < user.locked_until:
            raise AccountLocked(name)
        if not passwords.verify(password, user.salt, user.digest):
            user.failures += 1
            self.audit.append(f"failed login: {name}")
            if user.failures > MAX_FAILURES:
                user.locked_until = self.clock() + LOCK_SECONDS
                user.failures = 0
                raise AccountLocked(name)
            raise InvalidCredentials()
        user.failures = 0
        return self.sessions.create(name)

    def logout(self, token: str) -> None:
        self.sessions.revoke(token)

    def change_password(self, name: str, new_password: str) -> None:
        passwords.validate(new_password)
        user = self.users[name]
        user.salt, user.digest = passwords.hash_password(new_password)

    def admin_action(self, token: str, action: str) -> str:
        who = self.sessions.validate(token)
        if self.users[who].role != "admin":
            raise Forbidden(who)
        return f"{action} done"
