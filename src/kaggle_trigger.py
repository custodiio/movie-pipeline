"""
Módulo de Disparo Automatizado do Notebook no Kaggle via GitHub Actions Dispatch API
"""

import os
import requests
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "custodiio/movie-pipeline")

def trigger_kaggle_notebook(notebook_name: str = "movie_pipeline_master") -> bool:
    """Dispara a execução do notebook no Kaggle enviando um evento repository_dispatch para o GitHub Actions."""
    if not GITHUB_TOKEN:
        logging.error("GITHUB_TOKEN não configurada no .env.")
        return False

    url = f"https://api.github.com/repos/{GITHUB_REPO}/dispatches"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    payload = {
        "event_type": "run_kaggle_notebook",
        "client_payload": {
            "notebook": notebook_name
        }
    }

    logging.info(f"Disparando execução do notebook '{notebook_name}' no Kaggle via GitHub Dispatch ({GITHUB_REPO})...")
    res = requests.post(url, headers=headers, json=payload)
    
    if res.status_code == 204:
        logging.info("🚀 Disparo aceito! O GitHub Actions está injetando os secrets e acionando o notebook no Kaggle com GPU!")
        return True
    else:
        logging.error(f"Falha ao disparar GitHub Dispatch ({res.status_code}): {res.text}")
        return False
