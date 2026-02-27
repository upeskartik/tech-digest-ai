from sqlalchemy import Column, Integer, String, ForeignKey, JSON
from sqlalchemy.orm import relationship
from database import Base
from sqlalchemy.dialects.postgresql import JSONB


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    frequency = Column(String, default="daily", nullable=False)  # daily, weekly, monthly

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
    embedding = Column(JSONB)