import secrets
from dataclasses import dataclass
from typing import Callable

from gateway.errors import SessionExpired

SESSION_TTL = 30 * 60


@dataclass
class Session:
    user: str
    created_at: float
    last_seen: float


class SessionStore:
    def __init__(self, clock: Callable[[], float]) -> None:
        self.clock = clock
        self.sessions: dict[str, Session] = {}

    def create(self, user: str) -> str:
        token = secrets.token_hex(16)
        now = self.clock()
        self.sessions[token] = Session(user, now, now)
        return token

    def validate(self, token: str) -> str:
        session = self.sessions.get(token)
        if session is None:
            raise SessionExpired()
        if self.clock() - session.created_at > SESSION_TTL:
            del self.sessions[token]
            raise SessionExpired()
        session.last_seen = self.clock()
        return session.user

    def revoke(self, token: str) -> None:
        self.sessions.pop(token, None)

    def revoke_all(self, user: str) -> None:
        for token in [t for t, s in self.sessions.items() if s.user == user]:
            del self.sessions[token]
