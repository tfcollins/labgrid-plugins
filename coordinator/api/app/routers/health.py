from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request):
    coordinator = request.app.state.coordinator
    return {
        "status": "ok",
        "coordinator_connected": coordinator.connected,
        "coordinator_address": coordinator.address,
    }
