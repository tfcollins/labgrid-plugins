from fastapi import APIRouter, Request

from ..models import ExporterModel, ResourceModel

router = APIRouter(tags=["resources"])


@router.get("/resources", response_model=list[ResourceModel])
async def list_resources(
    request: Request,
    exporter: str | None = None,
    cls: str | None = None,
    avail: bool | None = None,
):
    return request.app.state.coordinator.get_resources(
        exporter_filter=exporter,
        cls_filter=cls,
        avail_filter=avail,
    )


@router.get("/exporters", response_model=list[ExporterModel])
async def list_exporters(request: Request):
    return request.app.state.coordinator.get_exporters()
