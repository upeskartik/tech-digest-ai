from tasks import ingest_posts
from database import SessionLocal

db = SessionLocal()
ingest_posts(db)