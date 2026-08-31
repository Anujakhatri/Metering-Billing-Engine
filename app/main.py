from fastapi import FastAPI
from app.routers import billing
from app.database import Base, engine

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI()

app.include_router(billing.router, prefix="/billing", tags=["billing"])

@app.get("/")
def read_root():
    return {"status": "Metering Engine Online"}
