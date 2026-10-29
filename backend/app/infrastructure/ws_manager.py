from typing import Any, Protocol

from contracts.ws import WebSocketMessage


class SocketLike(Protocol):
    async def accept(self) -> None: ...

    async def send_json(self, data: dict[str, Any]) -> None: ...


class WsManager:
    # shortcut: in-process registry; add pub/sub when the API scales past one worker.
    def __init__(self) -> None:
        self._sockets: list[SocketLike] = []

    async def connect(self, websocket: SocketLike) -> None:
        await websocket.accept()
        self._sockets.append(websocket)

    def disconnect(self, websocket: SocketLike) -> None:
        if websocket in self._sockets:
            self._sockets.remove(websocket)

    async def broadcast(self, message: WebSocketMessage) -> None:
        data = message.model_dump(mode="json")
        for websocket in list(self._sockets):
            try:
                await websocket.send_json(data)
            except Exception:  # noqa: BLE001 - a dead socket must not stop the rest
                self.disconnect(websocket)


ws_manager = WsManager()
