from tasks import ingest_posts
from database import SessionLocal
from tasks import update_core_embeddings, update_behavior_embeddings
from sqlalchemy import text
from worker import celery, send_email
from datetime import datetime, timedelta
db = SessionLocal()

def send_email_to_user(user_id):
    posts = db.execute(
        text("""
            SELECT id, url, title, published_at, summary, embedding
            FROM posts
        """)
    ).fetchall()
    post = posts[-1]
    url = post[1]
    print(url)
    title = post[2]
    published_at = datetime.fromisoformat(post[3])
    summary = post[4]
    embedding = post[5]
    tracked_link = (
        f"http://localhost:8000/track-click"
        f"?user_id={user_id}&url={url}"
    )
    text_body = f"Your daily Tech Digest\n\n"
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height:1.6;">
        <h2>🔥 Your daily Tech Digest</h2>
        <hr>
    """
    text_body += f"- {title}\n"
    text_body += f"{summary}\n"
    text_body += f"{tracked_link}\n\n"

    html_body += f"""
        <div style="margin-bottom:30px;">
            <h3>{title}</h3>
            <p style="white-space:pre-line;">{summary}</p>
            <a href="{tracked_link}" style="color:#1a73e8;">
                Read full article →
            </a>
        </div>
    """

    # Mark original URL as sent (NOT tracked link)
    db.execute(
        text("""
            INSERT INTO sent_posts (user_id, post_url)
            VALUES (:uid, :url)
        """),
        {"uid": user_id, "url": url}
    )

    html_body += "</body></html>"

    send_email(
        "kartik2598@gmail.com",
        f"Your Daily Tech Digest",
        text_body,
        html_body
    )

    db.commit()

# update_behavior_embeddings()
send_email_to_user(1)
