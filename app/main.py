from fastapi import FastAPI
from app.routers import billing, webhooks, checkout
from app.database import Base, engine

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI()


app.include_router(billing.router, prefix="/billing", tags=["billing"])
app.include_router(webhooks.router, tags=["webhooks"])
app.include_router(checkout.router, tags=["checkout"])

@app.get("/")
def read_root():
    return {"status": "Metering Engine Online"}

