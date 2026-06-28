from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi_jwt_auth2.exceptions import AuthJWTException

from app.api.order_routes import router as order_router
from app.core import jwt_config  # noqa: F401

app = FastAPI(title="Order Service")
app.include_router(order_router)


@app.exception_handler(AuthJWTException)
def authjwt_exception_handler(request: Request, exc: AuthJWTException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
