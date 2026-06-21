# from fastapi import FastAPI

# app = FastAPI(title="User Service")


# @app.get("/health")
# async def health():
#     return {"status": "ok"}

from fastapi import FastAPI
from app.api.user_routes import router as user_router
from app.core import jwt_config  # noqa: F401 — import triggers @AuthJWT.load_config registration

app = FastAPI(title="User Service")
app.include_router(user_router)


@app.get("/health")
async def health():
    return {"status": "ok"}