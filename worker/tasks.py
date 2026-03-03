from datetime import datetime, timedelta
import traceback
# from turtle import update
import feedparser
import json
import numpy as np
import helper
from worker import celery, send_email
from database import SessionLocal
from sqlalchemy import text
import logging
import asyncio

from ai_utils import generate_summary
from ai_embeddings import get_embedding, cosine_similarity


RSS_FEEDS = [
    "https://dev.to/feed",
    "https://hnrss.org/frontpage",
]

def update_core_embeddings(user_id):
    db = SessionLocal()
    user_preferences = db.execute(text("""
                            SELECT keyword from interests where user_id = :user_id
                        """), {
                            "user_id": user_id
                        })
    preference_text = ""
    for prefer in user_preferences:
        preference_text += prefer[0] + ""
    # Clean & embed user input
    structured_text = f"""
    User selected following topic preferences:
    {preference_text}
    """
    core_embedding = get_embedding(structured_text)
    print(type(core_embedding))
    # core_embedding = np.array(core_embedding)
    print(type(core_embedding))
    db.execute(
            text("""
                UPDATE users
                SET core_embedding = :core_embedding
                WHERE id = :uid
            """),
            {
                "core_embedding": json.dumps(core_embedding),
                "uid": user_id
            }
    )
    db.commit()
    db.close()
    return core_embedding

# def update_interest(db):


def ingest_posts(db):
    """
    Fetch RSS feeds.
    Store posts in DB with embedding + summary (only once).
    """

    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)

        for entry in feed.entries:

            if not hasattr(entry, "published_parsed"):
                continue

            published = datetime(*entry.published_parsed[:6])
            url = entry.link

            existing = db.execute(
                text("SELECT id FROM posts WHERE url = :url"),
                {"url": url}
            ).fetchone()

            if existing:
                continue  # already cached

            article_text = f"{entry.title} {getattr(entry, 'summary', '')}"

            # try:
            embedding = get_embedding(article_text)
            logging.info(f"article_text: {str(article_text)}")
            logging.info(f"article_embedding: {str(embedding)}")
            summary = generate_summary(entry.title, url)
            # except Exception as e:
            #     print("Embedding/Summary error:", e)
            #     continue
            
            db.execute(
                text("""
                    INSERT INTO posts (url, title, published_at, summary, embedding)
                    VALUES (:url, :title, :published, :summary, :embedding)
                    ON CONFLICT (url) DO NOTHING
                """),
                {
                    "url": url,
                    "title": entry.title,
                    "published": str(published),
                    "summary": summary,
                    "embedding": json.dumps(embedding),
                }
            )
            db.commit()
        

    print("Post ingestion complete.")

def process_digest(frequency, days_back, max_posts):
    db = SessionLocal()

    users = db.execute(
        text("""
            SELECT id,
                   email,
                   core_embedding,
                   behavior_embedding
            FROM users
            WHERE LOWER(frequency) = :freq
        """),
        {"freq": frequency.lower()}
    ).fetchall()

    print(f"Processing {frequency} users:", users)

    now = datetime.utcnow()
    cutoff = now - timedelta(days=days_back)

    posts = db.execute(
        text("""
            SELECT id, url, title, published_at, summary, embedding
            FROM posts
        """)
    ).fetchall()

    for user in users:
        user_id = user[0]
        user_email = user[1]

        core_embedding = user[2] or []
        if len(core_embedding) == 0:
            core_embedding = update_core_embeddings(user_id)
        behavior_embedding = user[3] or []

        if not core_embedding and not behavior_embedding:
            print(f"No embeddings found for {user_email}")
            continue

        # Convert to numpy
        core = np.array(core_embedding) if core_embedding else None
        behavior = np.array(behavior_embedding) if behavior_embedding else None

        # Normalize helper
        def normalize(v):
            norm = np.linalg.norm(v)
            return v / norm if norm > 0 else v

        if core is not None:
            core = normalize(core)

        if behavior is not None:
            behavior = normalize(behavior)

        # Combine embeddings
        if core is not None and behavior is not None:
            final_user_vector = (0.6 * core) + (0.4 * behavior)
        elif core is not None:
            final_user_vector = core
        else:
            final_user_vector = behavior

        ranked_posts = []

        for post in posts:
            post_id = post[0]
            url = post[1]
            title = post[2]
            published_at = datetime.fromisoformat(post[3])
            summary = post[4]
            embedding = post[5]

            if published_at < cutoff:
                continue

            # Prevent duplicate sends
            already_sent = db.execute(
                text("""
                    SELECT 1 FROM sent_posts
                    WHERE user_id = :uid AND post_url = :url
                """),
                {"uid": user_id, "url": url}
            ).fetchone()

            if already_sent:
                continue

            if not embedding:
                continue

            if isinstance(embedding, str):
                embedding = json.loads(embedding)

            post_vector = np.array(embedding)
            post_vector = normalize(post_vector)

            similarity = cosine_similarity(final_user_vector, post_vector)

            days_old = (datetime.utcnow() - published_at).days
            freshness_score = 1 / (1 + days_old)

            final_score = (similarity * 0.8) + (freshness_score * 0.2)

            if final_score < 0.65:
                continue

            ranked_posts.append({
                "title": title,
                "link": url,
                "summary": summary,
                "score": final_score
            })

        ranked_posts = sorted(
            ranked_posts,
            key=lambda x: x["score"],
            reverse=True
        )[:max_posts]

        if not ranked_posts:
            print(f"No relevant posts for {user_email}")
            continue

        text_body = f"Your {frequency.capitalize()} Tech Digest\n\n"
        html_body = f"""
        <html>
          <body style="font-family: Arial, sans-serif; line-height:1.6;">
            <h2>🔥 Your {frequency.capitalize()} Tech Digest</h2>
            <hr>
        """

        for post in ranked_posts:
            tracked_link = (
                f"http://localhost:8000/track-click"
                f"?user_id={user_id}&url={post['link']}"
            )

            text_body += f"- {post['title']}\n"
            text_body += f"{post['summary']}\n"
            text_body += f"{tracked_link}\n\n"

            html_body += f"""
                <div style="margin-bottom:30px;">
                    <h3>{post['title']}</h3>
                    <p style="white-space:pre-line;">{post['summary']}</p>
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
                {"uid": user_id, "url": post["link"]}
            )

        html_body += "</body></html>"

        send_email(
            user_email,
            f"Your {frequency.capitalize()} Tech Digest",
            text_body,
            html_body
        )

        db.commit()

        print(f"Sent {frequency} digest to {user_email}")

    db.close()




@celery.task
def daily_digest():
    process_digest("daily", days_back=1, max_posts=2)


@celery.task
def weekly_digest():
    process_digest("weekly", days_back=7, max_posts=6)


@celery.task
def monthly_digest():
    process_digest("monthly", days_back=30, max_posts=10)

@celery.task
def ingest_posts_task():
    db = SessionLocal()
    ingest_posts(db)
    db.close()

@celery.task
def update_behavior_embeddings():
    db = SessionLocal()

    users = db.execute(
        text("""
            SELECT id, behavior_embedding, behavior_click_count,
                   last_behavior_update_at
            FROM users
            WHERE needs_behavior_update = true
            LIMIT 500
        """)
    ).fetchall()

    for user in users:
        uid = user.id

        # Fetch new clicks
        if user.last_behavior_update_at:
            clicks = db.execute(
                text("""
                    SELECT post_url FROM clicks
                    WHERE user_id = :uid
                    AND created_at > :last_update
                """),
                {"uid": uid, "last_update": user.last_behavior_update_at}
            ).fetchall()
        else:
            clicks = db.execute(
                text("""
                    SELECT post_url FROM clicks
                    WHERE user_id = :uid
                """),
                {"uid": uid}
            ).fetchall()

        if not clicks:
            continue

        # Get embeddings for clicked posts
        post_embeddings = []
        for row in clicks:
            post = db.execute(
                text("""
                    SELECT embedding FROM posts
                    WHERE url = :url
                """),
                {"url": row.post_url}
            ).fetchone()

            if post and post.embedding:
                emb = post.embedding
                if isinstance(emb, dict):
                    emb = emb.get("embedding", [])
                post_embeddings.append(emb)

        if not post_embeddings:
            continue

        new_avg = np.mean(post_embeddings, axis=0)

        old_emb = user.behavior_embedding or []
        old_count = user.behavior_click_count or 0
        new_count = len(post_embeddings)

        if old_emb:
            old_emb = np.array(old_emb)
            updated = ((old_emb * old_count) + (new_avg * new_count)) / (old_count + new_count)
        else:
            updated = new_avg

        db.execute(
            text("""
                UPDATE users
                SET behavior_embedding = :emb,
                    behavior_click_count = :count,
                    last_behavior_update_at = NOW(),
                    needs_behavior_update = false
                WHERE id = :uid
            """),
            {
                "emb": updated.tolist(),
                "count": old_count + new_count,
                "uid": uid,
            }
        )

    db.commit()
    db.close()