from sqlalchemy import Column, Integer, String, ForeignKey, JSON, DateTime, Float, Boolean
from sqlalchemy.orm import relationship
from app.database import Base
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
from pgvector.sqlalchemy import Vector

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    frequency = Column(String, default="daily", nullable=False)  # daily, weekly, monthly
    # Long Term
    core_embedding = Column(Vector(1024), nullable=True)

    #Behavior
    behavior_embedding = Column(Vector(1024), nullable=True)
    behavior_click_count = Column(Integer, default=0)
    last_behavior_update_at = Column(DateTime, nullable=True)
    needs_behavior_update = Column(Boolean, default=False)

    # EXPLICIT (future)
    # explicit_embedding = Column(JSONB, nullable=True)
    # explicit_weight = Column(Float, default=0.0)
    # explicit_expires_at = Column(DateTime, nullable=True)
    # Relationships
    interests = relationship(
        "Interest",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    sent_posts = relationship(
        "SentPost",
        back_populates="user",
        cascade="all, delete-orphan"
    )


class Interest(Base):
    __tablename__ = "interests"

    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))

    user = relationship("User", back_populates="interests")


class SentPost(Base):
    __tablename__ = "sent_posts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    post_url = Column(String, nullable=False)

    user = relationship("User", back_populates="sent_posts")

# class Post(Base):
#     __tablename__ = "posts"

#     id = Column(Integer, primary_key=True, index=True)
#     url = Column(String, unique=True, nullable=False)
#     title = Column(String, nullable=False)
#     published_at = Column(String)
#     summary = Column(String)  # AI generated summary
#     embedding = Column(JSON)

class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, index=True, nullable=False)
    title = Column(String, nullable=False)
    published_at = Column(String)
    summary = Column(String)
    embedding = Column(Vector(1024))

class Click(Base):
    __tablename__ = "clicks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    post_url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)