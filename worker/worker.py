from celery import Celery
import smtplib
from email.mime.text import MIMEText
import os
from celery.schedules import crontab
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart

celery = Celery(
    "tasks",
    broker="redis://redis:6379/0",
)
celery.conf.worker_concurrency = 1
celery.conf.result_backend = "redis://redis:6379/0"
celery.conf.timezone = "Asia/Kolkata"
celery.conf.beat_schedule = {
#update_behavior_embeddings
    "update-behavior-embeddings": {
        "task": "worker.tasks.update_behavior_embeddings",
        # "schedule": crontab(hour=9, minute=0),  # daily at 9 AM
        "schedule": 60.0,
    },
    "ingest-posts-every-5-hours": {
        "task": "worker.tasks.ingest_posts_task",
        "schedule": 900.0,   # 5 hours
    },
    "daily-digest": {
        "task": "worker.tasks.daily_digest",
        # "schedule": crontab(hour=9, minute=0),  # daily at 9 AM
        "schedule": 600.0,
    },
    "weekly-digest": {
        "task": "tasks.weekly_digest",
        "schedule": crontab(hour=9, minute=0, day_of_week=1),  # Monday 9 AM
    },
    "monthly-digest": {
        "task": "worker.tasks.monthly_digest",
        "schedule": crontab(hour=9, minute=0, day_of_month=1),  # 1st of month
    },
}


def send_email(to_email, subject, text_body, html_body):
    email_user = os.getenv("EMAIL_USER")
    email_pass = os.getenv("EMAIL_PASS")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_user
    msg["To"] = to_email

    part1 = MIMEText(text_body, "plain")
    part2 = MIMEText(html_body, "html")

    msg.attach(part1)
    msg.attach(part2)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(email_user, email_pass)
        server.sendmail(email_user, to_email, msg.as_string())

    print(f"HTML Email sent to {to_email}")