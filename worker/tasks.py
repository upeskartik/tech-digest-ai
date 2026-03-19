from datetime import datetime, timedelta, timezone
import traceback
# from turtle import update
import feedparser
import json
import numpy as np
from sqlalchemy.orm import Session
from app.models import User, Post, SentPost, Click
from worker.worker import celery, send_email
from worker.database import SessionLocal
from sqlalchemy import text
import logging
import asyncio
from sqlalchemy import func
from worker.helper import has_embedding

from worker.ai_utils import generate_summary
from worker.ai_embeddings import get_embedding, cosine_similarity


RSS_FEEDS = [
    "https://dev.to/feed",
    "https://hnrss.org/frontpage",
]

def update_core_embeddings(user_id: int):
    db: Session = SessionLocal()
    try:
        # 1. Fetch preferences
        preferences = db.execute(
            text("""
                SELECT keyword 
                FROM interests 
                WHERE user_id = :user_id
            """),
            {"user_id": user_id}
        ).fetchall()

        if not preferences:
            return None
        
        # 2. Build structured text (important for good embeddings)
        preference_list = [row[0] for row in preferences]

        structured_text = f"""
        User is interested in the following topics:
        {", ".join(preference_list)}
        """

        # 3. Generate embedding
        embedding = get_embedding(structured_text)

        # 4. Normalize (VERY IMPORTANT for cosine similarity)
        embedding = np.array(embedding)
        embedding = embedding / np.linalg.norm(embedding)

        # 5. Store using ORM (no json.dumps)
        user = db.get(User, user_id)
        user.core_embedding = embedding.tolist()

        db.commit()

        return user.core_embedding
    finally:
        db.close()
# def update_core_embeddings(user_id):
#     db = SessionLocal()
#     user_preferences = db.execute(text("""
#                             SELECT keyword from interests where user_id = :user_id
#                         """), {
#                             "user_id": user_id
#                         })
#     preference_text = ""
#     for prefer in user_preferences:
#         preference_text += prefer[0] + ""
#     # Clean & embed user input
#     structured_text = f"""
#     User selected following topic preferences:
#     {preference_text}
#     """
#     core_embedding = get_embedding(structured_text)
#     db.execute(
#             text("""
#                 UPDATE users
#                 SET core_embedding = :core_embedding
#                 WHERE id = :uid
#             """),
#             {
#                 "core_embedding": json.dumps(core_embedding),
#                 "uid": user_id
#             }
#     )
#     db.commit()
#     db.close()
#     return core_embedding

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
            # logging.info(f"article_text: {str(article_text)}")
            # logging.info(f"article_embedding: {str(embedding)}")
            embedding = np.array(embedding)
            embedding = embedding / np.linalg.norm(embedding)
            summary = generate_summary(entry.title, url)
            # except Exception as e:
            #     print("Embedding/Summary error:", e)
            #     continue
            
            post = Post(
                url=url,
                title=entry.title,
                published_at=str(published),
                summary=summary,
                embedding=embedding.tolist()
            )

            db.add(post)
            db.commit()
            # db.execute(
            #     text("""
            #         INSERT INTO posts (url, title, published_at, summary, embedding)
            #         VALUES (:url, :title, :published, :summary, :embedding::vector)
            #         ON CONFLICT (url) DO NOTHING
            #     """),
            #     {
            #         "url": url,
            #         "title": entry.title,
            #         "published": str(published),
            #         "summary": summary,
            #         "embedding": embedding.tolist(),
            #     }
            # )
            # db.commit()
        

    print("Post ingestion complete.")

def process_digest(frequency, days_back, max_posts):
    db = SessionLocal()

    # users = db.execute(
    #     text("""
    #         SELECT id,
    #                email,
    #                core_embedding,
    #                behavior_embedding
    #         FROM users
    #         WHERE LOWER(frequency) = :freq
    #     """),
    #     {"freq": frequency.lower()}
    # ).fetchall()
    users = db.query(User).filter(
            func.lower(User.frequency) == frequency.lower()
        ).all()
    print(f"Processing {frequency} users:", users)

    now = datetime.utcnow()
    cutoff = now - timedelta(days=days_back)

    # posts = db.execute(
    #     text("""
    #         SELECT id, url, title, published_at, summary, embedding
    #         FROM posts
    #     """)
    # ).fetchall()
    logging.info(f"process digest started")
    posts = db.query(Post).all()
    for user in users:
        user_id = user.id
        user_email = user.email
        # logging.info(f"process starte   d for {user_email}")
        # logging.info(f"core embedding: {user.core_embedding}")
        core_embedding = user.core_embedding if user.core_embedding is not None else []
        if len(core_embedding) == 0:
            core_embedding = update_core_embeddings(user_id)
        behavior_embedding = user.behavior_embedding if user.behavior_embedding is not None else []
        # logging.info(f"core embedding: {core_embedding}")
        if not has_embedding(core_embedding) and not has_embedding(behavior_embedding):
            print(f"No embeddings found for {user_email}")
            continue
        # logging.info(f"length of core embedding {len(core_embedding)}")
        # logging.info(f"core embedding is not None: {core_embedding is not None}")
        # logging.info(f"core embedding np array {np.array(core_embedding)}")
        # Convert to numpy
        core = np.array(core_embedding) if core_embedding is not None and len(core_embedding) > 0 else None
        behavior = np.array(behavior_embedding) if behavior_embedding is not None and len(behavior_embedding) > 0 else None
        # logging.info(f"core embedding: {core}")
        # Normalize helper
        def normalize(v):
            norm = np.linalg.norm(v)
            return v / norm if norm > 0 else v

        if core is not None:
            core = normalize(core)
        logging.info(f"core: {core}")
        if behavior is not None:
            behavior = normalize(behavior)

        # Combine embeddings
        if core is not None and behavior is not None:
            final_user_vector = (0.6 * core) + (0.4 * behavior)
        elif core is not None:
            final_user_vector = core
        elif behavior is not None:
            final_user_vector = behavior
        else:
            # logging.info(f"no embedding found {core}, {behavior}")
            continue

        ranked_posts = []
        # logging.info(f"total posts: {len(posts)}")
        for post in posts:
            # logging.info(f"processing post {post.url}")
            post_id = post.id
            url = post.url
            title = post.title
            published_at = datetime.fromisoformat(post.published_at)
            summary = post.summary
            embedding = post.embedding

            if published_at < cutoff:
                continue

            # Prevent duplicate sends
            # already_sent = db.execute(
            #     text("""
            #         SELECT 1 FROM sent_posts
            #         WHERE user_id = :uid AND post_url = :url
            #     """),
            #     {"uid": user_id, "url": url}
            # ).fetchone()
            already_sent = db.query(SentPost).filter(
                SentPost.user_id == user_id,
                SentPost.post_url == url
            ).first()
            if already_sent:
                continue

            # if not embedding:
            #     continue
            if not has_embedding(embedding):
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
            logging.info(f"processed post {post.url}")

        ranked_posts = sorted(
            ranked_posts,
            key=lambda x: x["score"],
            reverse=True
        )[:max_posts]
        # logging.info(f"number of posts found: {len(ranked_posts)}")
        if not ranked_posts:
            # logging.info(f"No relevant posts for {user_email}")
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
            # db.execute(
            #     text("""
            #         INSERT INTO sent_posts (user_id, post_url)
            #         VALUES (:uid, :url)
            #     """),
            #     {"uid": user_id, "url": post["link"]}
            # )
            sent_post = SentPost(
                user_id=user_id,
                post_url=post["link"]
            )

            db.add(sent_post)

        html_body += "</body></html>"

        send_email(
            user_email,
            f"Your {frequency.capitalize()} Tech Digest",
            text_body,
            html_body
        )
        db.commit()

        logging.info(f"Sent {frequency} digest to {user_email}")

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

    # db.execute(
    #     text("""
    #         SELECT id, behavior_embedding, behavior_click_count,
    #                last_behavior_update_at
    #         FROM users
    #         WHERE needs_behavior_update = true
    #         LIMIT 500
    #     """)
    # ).fetchall()
    users = db.query(User).filter(
                User.needs_behavior_update == True
            ).limit(500).all()
    logging.info(f"total number of users: {len(users)}")
    for user in users:
        uid = user.id

        # Fetch new clicks
        if user.last_behavior_update_at:
            # clicks = db.execute(
            #     text("""
            #         SELECT post_url FROM clicks
            #         WHERE user_id = :uid
            #         AND created_at > :last_update
            #     """),
            #     {"uid": uid, "last_update": user.last_behavior_update_at}
            # ).fetchall()
            clicks = db.query(Click.post_url).filter(
                Click.user_id == uid, 
                Click.created_at == user.last_behavior_update_at 
            ).all()
        else:
            # clicks = db.execute(
            #     text("""
            #         SELECT post_url FROM clicks
            #         WHERE user_id = :uid
            #     """),
            #     {"uid": uid}
            # ).fetchall()
            clicks = db.query(Click.post_url).filter(
                Click.user_id == uid
            ).all()
        logging.info(f"total clicks: {len(clicks)}")
        if not clicks:
            continue

        # Get embeddings for clicked posts
        post_embeddings = []
        for row in clicks:
            # post = db.execute(
            #     text("""
            #         SELECT embedding FROM posts
            #         WHERE url = :url
            #     """),
            #     {"url": row.post_url}
            # ).fetchone()
            post = db.query(Post.embedding).filter(
                Post.url == row.post_url
            ).first()
            if len(post) == 0:
                continue
            if has_embedding(post.embedding) :
                emb = post.embedding
                # logging.info(f"type of emp: {type(post.embedding)}")
                # if isinstance(emb, dict):
                #     emb = emb.get("embedding", [])
                post_embeddings.append(emb)
        logging.info(f"total embeddings: {len(post_embeddings)}")
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
        # db.execute(
        #     text("""
        #         UPDATE users
        #         SET behavior_embedding = :emb,
        #             behavior_click_count = :count,
        #             last_behavior_update_at = NOW(),
        #             needs_behavior_update = false
        #         WHERE id = :uid
        #     """),
        #     {
        #         "emb": updated.tolist(),
        #         "count": old_count + new_count,
        #         "uid": uid,
        #     }
        # )
        user.behavior_embedding = updated.tolist()
        user.behavior_click_count = old_count + new_count
        user.needs_behavior_update = False
        user.last_behavior_update_at = datetime.now(timezone.utc)

    db.commit()
    db.close()
