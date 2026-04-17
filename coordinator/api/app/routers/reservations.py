from fastapi import APIRouter, Depends, Request

from ..auth.dependencies import current_user
from ..auth.store import User
from ..models import CreateReservationRequest, ReservationModel

router = APIRouter(tags=["reservations"])


@router.get("/reservations", response_model=list[ReservationModel])
async def list_reservations(request: Request):
    return await request.app.state.coordinator.get_reservations()


@router.post("/reservations", response_model=ReservationModel, status_code=201)
async def create_reservation(
    body: CreateReservationRequest, request: Request, _user: User = Depends(current_user)
):
    return await request.app.state.coordinator.create_reservation(body.filters, body.prio)


@router.delete("/reservations/{token}", status_code=204)
async def cancel_reservation(token: str, request: Request, _user: User = Depends(current_user)):
    await request.app.state.coordinator.cancel_reservation(token)


@router.post("/reservations/{token}/poll", response_model=ReservationModel)
async def poll_reservation(token: str, request: Request, _user: User = Depends(current_user)):
    return await request.app.state.coordinator.poll_reservation(token)
