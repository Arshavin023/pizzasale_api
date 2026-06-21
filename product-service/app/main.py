from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi_jwt_auth2.exceptions import AuthJWTException

from app.api.category_routes import router as category_router
from app.api.product_routes import router as product_router
from app.core import jwt_config  # noqa: F401 — triggers @AuthJWT.load_config registration

app = FastAPI(title="Product Service")
app.include_router(category_router)
app.include_router(product_router)


@app.exception_handler(AuthJWTException)
def authjwt_exception_handler(request: Request, exc: AuthJWTException):
    # Without this, any JWT failure (missing token, expired token, bad
    # signature) is an unhandled exception type FastAPI doesn't know
    # how to format — it falls through as a bare 500 instead of the
    # correct 401/403 with a real error body.
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}