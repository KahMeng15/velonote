from app.utils.db import SessionLocal
from app.models.db import User

db = SessionLocal()
user = db.query(User).filter(User.id == 1).first()
if user:
    print(f"Use global AI config: {user.use_global_ai_config}")
    print(f"User AI Provider: {user.ai_provider}")
    print(f"User AI Model: {user.ai_model}")
