from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.infrastructure.ws_manager import ws_manager

router = APIRouter(tags=["ws"])


@router.websocket("/ws", name="execution_socket")
async def execution_socket(websocket: WebSocket) -> None:
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
