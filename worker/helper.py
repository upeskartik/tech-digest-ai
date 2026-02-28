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