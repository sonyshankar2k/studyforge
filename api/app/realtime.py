"""WebSocket hub: tells everyone viewing a study when something changes.

Clients connect to /ws/studies/{id}. After any save, the API broadcasts a small
event; the Angular app then refetches (REST stays the source of truth).

Note: this in-memory hub only works with ONE API process. To scale to several
pods on Kubernetes, publish events through Redis pub/sub instead (good
interview talking point, and a planned Week 2 upgrade).
"""

from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class StudyHub:
    def __init__(self) -> None:
        self._rooms: dict[int, set[WebSocket]] = defaultdict(set)

    async def join(self, study_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self._rooms[study_id].add(ws)

    def leave(self, study_id: int, ws: WebSocket) -> None:
        self._rooms[study_id].discard(ws)

    async def broadcast(self, study_id: int, event: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in self._rooms[study_id]:
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.leave(study_id, ws)


hub = StudyHub()
