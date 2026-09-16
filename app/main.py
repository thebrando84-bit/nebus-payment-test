from fastapi import Depends, FastAPI

from app.core.security import require_api_key
from app.payments.router import router as payments_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Async Payment Processing Service",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.include_router(payments_router)

    @app.get("/health", dependencies=[Depends(require_api_key)])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
