from fastapi import FastAPI
from app.api.payment_routes import router as payment_router

app = FastAPI(title="Payment Service")
app.include_router(payment_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
