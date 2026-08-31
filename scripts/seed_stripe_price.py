from app.database import SessionLocal
from app.models import Plan

db = SessionLocal()
pro_plan = db.query(Plan).filter(Plan.name == "pro").first()

if not pro_plan:
    raise Exception("Pro plan not found — run your plan seed script first")

pro_plan.stripe_price_id = "price_1UAXZ0CvZDABhS1TVtYZM9xs"
db.commit()
print(f"Updated: {pro_plan.name} → {pro_plan.stripe_price_id}")

db.close()