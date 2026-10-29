from fastapi import APIRouter

from app.api.routes import cameras, runtimes, sops, stations, utils

api_router = APIRouter()
api_router.include_router(utils.router)
api_router.include_router(sops.router)
api_router.include_router(stations.router)
api_router.include_router(cameras.router)
api_router.include_router(runtimes.router)
