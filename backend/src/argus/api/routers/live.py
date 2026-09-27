from __future__ import annotations

from fastapi import APIRouter

from argus.domain.live_video import CHANNELS, WEBCAMS, Channel, Webcam

router = APIRouter(prefix="/live", tags=["live"])


@router.get("/channels", response_model=list[Channel])
async def list_channels() -> list[Channel]:
    """Live TV news channels, each with its streams in order of preference."""
    return list(CHANNELS)


@router.get("/webcams", response_model=list[Webcam])
async def list_webcams() -> list[Webcam]:
    """Live city webcams (YouTube), placed where they film."""
    return list(WEBCAMS)
