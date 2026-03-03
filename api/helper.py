import requests
OLLAMA_EMBED_URL = "http://host.docker.internal:11434/api/embeddings"
MODEL = "mxbai-embed-large:latest"


from bs4 import BeautifulSoup
import re

def clean_text(text):
    if not isinstance(text, str):
        return ""

    # Remove HTML
    soup = BeautifulSoup(text, "html.parser")
    clean = soup.get_text(separator=" ")

    # Remove LaTeX blocks
    clean = re.sub(r"\$\$.*?\$\$", " ", clean, flags=re.DOTALL)

    # Remove extra whitespace
    clean = re.sub(r"\s+", " ", clean)

    return clean.strip()

def get_embedding(text):
    try:
        if not isinstance(text, str) or not text.strip():
            return []

        text = clean_text(text)

        MAX_CHARS = 1500
        text = text[:MAX_CHARS]
        response = requests.post(
            OLLAMA_EMBED_URL,
            json={
                "model": MODEL,
                "prompt": text
            },
            timeout=120
        )

        # print("STATUS:", response.status_code)
        # print("RAW:", response.text)   # 🔥 print full response

        response.raise_for_status()
        return response.json()['embedding']
    except Exception as e:
        print("Embedding failed.")
        print("Input length:", len(text) if isinstance(text, str) else "Not string")
        print("Input preview:", str(text)[:200])
        raise e