import os
from pydantic import BaseModel
from fastapi_jwt_auth2 import AuthJWT

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET is not set")

class Settings(BaseModel):
    authjwt_secret_key: str = JWT_SECRET

@AuthJWT.load_config
def get_config():
    return Settings()
