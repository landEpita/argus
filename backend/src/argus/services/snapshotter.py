"""Hourly snapshots of the Country Signal Index, so its evolution can be drawn."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from argus.services.analysis import AnalysisService

logger = logging.getLogger(__name__)

INTERVAL_S = 3600.0
FIRST_DELAY_S = 60.0  # let caches warm up after a restart


class SignalSnapshotter:
    name = "signal-snapshotter"

    def __init__(
        self,
        analysis: AnalysisService,
        interval_s: float = INTERVAL_S,
        first_delay_s: float = FIRST_DELAY_S,
    ) -> None:
        self._analysis = analysis
        self._interval_s = interval_s
        self._first_delay_s = first_delay_s
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name=self.name)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        await asyncio.sleep(self._first_delay_s)
        while True:
            try:
                stored = await self._analysis.snapshot()
                logger.info("signal snapshot stored", extra={"countries": stored})
            except asyncio.CancelledError:
                raise
            except Exception:  # a failed snapshot must not stop the next ones
                logger.exception("signal snapshot failed")
            await asyncio.sleep(self._interval_s)
