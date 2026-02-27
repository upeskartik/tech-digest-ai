import requests

OLLAMA_URL = "http://host.docker.internal:11434/api/generate"
MODEL = "llama3"


def generate_summary(title, link):
    prompt = f"""
    Summarize this tech article for developers.

    Provide:
    - One TLDR line
    - 3 key insights
    - Why it matters

    Title: {title}
    Link: {link}
    """

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False
        },
        timeout=120
    )

    response.raise_for_status()

    return response.json()["response"]