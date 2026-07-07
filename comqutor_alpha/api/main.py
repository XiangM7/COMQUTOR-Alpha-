"""Optional FastAPI app for COMQUTOR Week 1 API routes."""

from __future__ import annotations

try:
    from fastapi import FastAPI

    from comqutor_alpha.api.routes_alpha_library import router as alpha_library_router
    from comqutor_alpha.api.routes_research import router as research_router

    app = FastAPI(title="COMQUTOR Alpha API")

    for router in (
        alpha_library_router,
        research_router,
    ):
        if router is not None:
            app.include_router(router)

except ImportError:
    app = None
