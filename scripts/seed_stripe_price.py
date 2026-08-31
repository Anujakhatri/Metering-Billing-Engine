import sys
import os

sys.path.insert(0, os.path.abspath("."))

from app.database import SessionLocal, Base, engine
from app.models import Plan

# Ensure tables exist
Base.metadata.create_all(bind=engine)

db = SessionLocal()

pro_plan = db.query(Plan).filter(Plan.name == "pro").first()

if not pro_plan:
    print("Pro plan not found. Creating it now...")
    pro_plan = Plan(name="pro", api_call_limit=1000, ai_token_limit=10000, price_cents=2000)
    db.add(pro_plan)
    db.commit()
    db.refresh(pro_plan)

pro_plan.stripe_price_id = "price_1UAXZ0CvZDABhS1TVtYZM9xs"
db.commit()
print(f"Updated: {pro_plan.name} → {pro_plan.stripe_price_id}")

db.close()