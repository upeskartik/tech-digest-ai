import requests
import numpy as np
import helper
OLLAMA_EMBED_URL = "http://host.docker.internal:11434/api/embeddings"
MODEL = "mxbai-embed-large:latest"


def get_embedding(text):
    try:
        if not isinstance(text, str) or not text.strip():
            return []

        text = helper.clean_text(text)

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

def cosine_similarity(vec1, vec2):
    v1 = np.array(vec1)
    v2 = np.array(vec2)
    return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))