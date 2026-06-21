# import os
# from fastapi import FastAPI
# from app.api.auth_routes import router as auth_router
# from app.db.base import Base
# from app.db.session import engine
# import asyncio
# from fastapi_jwt_auth2 import AuthJWT
# from pydantic import BaseModel


# class Settings(BaseModel):
#     authjwt_secret_key:str = os.getenv("JWT_SECRET")

# @AuthJWT.load_config
# def get_config():
#     return Settings()

# app = FastAPI(title="Authentication Service")
# app.include_router(auth_router)

import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from app.api.auth_routes import router as auth_router
from app.db.base import Base
from app.db.session import engine
from fastapi_jwt_auth2 import AuthJWT
from fastapi_jwt_auth2.exceptions import AuthJWTException
from pydantic import BaseModel


class Settings(BaseModel):
    authjwt_secret_key: str = os.getenv("JWT_SECRET")

@AuthJWT.load_config
def get_config():
    return Settings()

app = FastAPI(title="Authentication Service")
app.include_router(auth_router)


@app.exception_handler(AuthJWTException)
def authjwt_exception_handler(request: Request, exc: AuthJWTException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )