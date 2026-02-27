from fastapi import FastAPI
from pydantic import BaseModel
from database import SessionLocal
import models
from models import User, Interest
from database import engine
from models import Base

Base.metadata.create_all(bind=engine)

app = FastAPI()

class RegisterRequest(BaseModel):
    email: str
    interests: list[str]
    frequency: str  # daily / weekly / monthly

@app.post("/register")
def register_user(data: RegisterRequest):
    db = SessionLocal()

    user = User(email=data.email)
    db.add(user)
    db.commit()
    db.refresh(user)

    for keyword in data.interests:
        db.add(Interest(user_id=user.id, keyword=keyword))

    db.commit()
    return {"message": "User registered successfully"}