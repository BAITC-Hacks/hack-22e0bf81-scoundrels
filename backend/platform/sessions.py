import asyncio
from dataclasses import dataclass, field
from uuid import uuid4
from contracts.models import Topic, TurnRecord

@dataclass
class Session:
    history: list[TurnRecord] = field(default_factory=list)
    topics: list[Topic] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

class SessionStore:
    """Single-process demo storage; not shared between server workers."""
    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def create(self) -> str:
        if len(self._sessions) >= 100:
            raise ValueError("Session capacity reached; restart the demo server")
        session_id = str(uuid4())
        self._sessions[session_id] = Session()
        return session_id

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)
