import uuid
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[uuid.UUID, set[WebSocket]] = defaultdict(set)

    async def connect(
        self, conversation_id: uuid.UUID, websocket: WebSocket
    ) -> None:
        await websocket.accept()
        self.connections[conversation_id].add(websocket)

    def disconnect(
        self, conversation_id: uuid.UUID, websocket: WebSocket
    ) -> None:
        connections = self.connections.get(conversation_id)
        if not connections:
            return
        connections.discard(websocket)
        if not connections:
            self.connections.pop(conversation_id, None)

    async def broadcast(
        self, conversation_id: uuid.UUID, payload: dict
    ) -> None:
        dead: list[WebSocket] = []
        for websocket in self.connections.get(conversation_id, set()).copy():
            try:
                await websocket.send_json(payload)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(conversation_id, websocket)


manager = ConnectionManager()
