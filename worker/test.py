from tasks import ingest_posts
from database import SessionLocal
from tasks import update_core_embeddings
db = SessionLocal()
update_core_embeddings(1)
ingest_posts(db)