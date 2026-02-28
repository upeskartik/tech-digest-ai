from datetime import datetime, timedelta
import feedparser
import json
import numpy as np
import helper
from worker import celery, send_email
from database import SessionLocal
from sqlalchemy import text

from ai_utils import generate_summary
from ai_embeddings import get_embedding, cosine_similarity


RSS_FEEDS = [
    "https://dev.to/feed",
    "https://hnrss.org/frontpage",
]


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

            try:
                embedding = get_embedding(article_text)
                summary = generate_summary(entry.title, url)
            except Exception as e:
                print("Embedding/Summary error:", e)
                continue
            
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

    # First ingest & cache new posts
    # ingest_posts(db)

    # Fetch users by frequency
    users = db.execute(
        text("SELECT id, email FROM users WHERE LOWER(frequency) = :freq"),
        {"freq": frequency.lower()}
    ).fetchall()

    print(f"Processing {frequency} users:", users)

    now = datetime.utcnow()
    cutoff = now - timedelta(days=days_back)

    # Fetch candidate posts once
    posts = db.execute(
        text("SELECT id, url, title, published_at, summary, embedding FROM posts")
    ).fetchall()

    for user in users:
        user_id = user[0]
        user_email = user[1]

        interests = db.execute(
            text("SELECT keyword FROM interests WHERE user_id = :uid"),
            {"uid": user_id}
        ).fetchall()

        keywords = [row[0] for row in interests]
        if not keywords:
            continue

        # Create user embedding ONCE
        # user_profile_text = " ".join(keywords)
        try:
            user_profile_text = f"""
                The user is a software engineer interested in:
                {", ".join(keywords)}.

                Topics include:
                containerization, Dockerfiles, images,
                Kubernetes, DevOps pipelines,
                microservices, backend architecture,
                deployment, CI/CD systems.
                """
            user_embedding = get_embedding(user_profile_text)
        except Exception as e:
            print("User embedding error:", e)
            continue

        ranked_posts = []
        scored_posts = []
        for post in posts:
            post_id = post[0]
            url = post[1]
            title = post[2]
            published_at = datetime.fromisoformat(post[3])
            summary = post[4]
            embedding = post[5]
            if published_at < cutoff:
                continue

            # Duplicate prevention
            already_sent = db.execute(
                text("""
                    SELECT 1 FROM sent_posts
                    WHERE user_id = :uid AND post_url = :url
                """),
                {"uid": user_id, "url": url}
            ).fetchone()

            if already_sent:
                continue

            similarity = cosine_similarity(user_embedding, embedding)
            days_old = (datetime.utcnow() - published_at).days
            freshness_score = 1 / (1 + days_old)

            final_score = (similarity * 0.8) + (freshness_score * 0.2)
            # Threshold filtering
            if final_score < 0.65:
                continue

            ranked_posts.append({
                "title": title,
                "link": url,
                "summary": summary,
                "score": final_score
            })

        # Sort by semantic similarity
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
            text_body += f"- {post['title']}\n"
            text_body += f"{post['summary']}\n"
            text_body += f"{post['link']}\n\n"

            html_body += f"""
                <div style="margin-bottom:30px;">
                    <h3>{post['title']}</h3>
                    <p style="white-space:pre-line;">{post['summary']}</p>
                    <a href="{post['link']}" style="color:#1a73e8;">
                        Read full article →
                    </a>
                </div>
            """

        html_body += "</body></html>"

        send_email(
            user_email,
            f"Your {frequency.capitalize()} Tech Digest",
            text_body,
            html_body
        )

        # Mark posts as sent
        for post in ranked_posts:
            db.execute(
                text("""
                    INSERT INTO sent_posts (user_id, post_url)
                    VALUES (:uid, :url)
                """),
                {"uid": user_id, "url": post["link"]}
            )

        db.commit()

        print(f"Sent {frequency} digest to {user_email}")




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