import requests
import numpy as np

OLLAMA_EMBED_URL = "http://host.docker.internal:11434/api/embed"
MODEL = "mxbai-embed-large:latest"


def get_embedding(text):
    response = requests.post(
        OLLAMA_EMBED_URL,
        json={
            "model": MODEL,
            "input": text
        },
        timeout=120
    )

    # print("STATUS:", response.status_code)
    # print("RAW:", response.text)   # 🔥 print full response

    response.raise_for_status()
    return response.json()["embeddings"][0]

def cosine_similarity(vec1, vec2):
    v1 = np.array(vec1)
    v2 = np.array(vec2)
    return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))