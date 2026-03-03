from requests import Session
from fastapi import FastAPI
from pydantic import BaseModel
from database import SessionLocal
import models
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from models import User, Interest, Post, Click, SentPost
from database import engine
from models import Base
from datetime import datetime, timedelta
from helper import get_embedding

Base.metadata.create_all(bind=engine)

app = FastAPI()
def get_db():
    db = SessionLocal()
    return db

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

@app.get("/track-click")
def track_click(user_id: int, url: str):
    db = SessionLocal()

    db.execute(
        text("""
            INSERT INTO clicks (user_id, post_url)
            VALUES (:uid, :url)
        """),
        {"uid": user_id, "url": url}
    )

    # Mark user dirty
    db.execute(
        text("""
            UPDATE users
            SET needs_behavior_update = true
            WHERE id = :uid
        """),
        {"uid": user_id}
    )

    db.commit()
    db.close()

    return RedirectResponse(url=url, status_code=302)

@app.post("/update-preference")
def update_preference(user_id: int, preference_text: str):
    db = SessionLocal()

    # Clean & embed user input
    structured_text = f"""
    User currently wants more content about:
    {preference_text}
    """

    embedding = get_embedding(structured_text)

    db.execute(
        text("""
            UPDATE users
            SET explicit_embedding = :embedding,
                explicit_weight = :weight,
                explicit_expires_at = :expiry
            WHERE id = :uid
        """),
        {
            "embedding": embedding,
            "weight": 0.7,  # strong but not dominant
            "expiry": datetime.utcnow() + timedelta(days=14),
            "uid": user_id,
        }
    )

    db.commit()
    db.close()

    return {"status": "Preference updated successfully"}