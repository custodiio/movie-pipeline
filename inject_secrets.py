"""
Injeta secrets do GitHub Actions diretamente no código-fonte do notebook .ipynb do Movie-Pipeline.
Roda no GitHub Actions ANTES do kaggle push.
"""
import json
import os
import sys

notebook_name = os.environ.get("NOTEBOOK", "movie_pipeline_master")
file_path = f"{notebook_name}.ipynb"
if not os.path.exists(file_path):
    file_path = os.path.join("notebooks", f"{notebook_name}.ipynb")

if not os.path.exists(file_path):
    print(f"ERRO: Notebook '{file_path}' não encontrado")
    sys.exit(1)

print(f"📄 Abrindo notebook para injeção de secrets: {file_path}")

with open(file_path, "r", encoding="utf-8") as f:
    nb = json.load(f)

# Mapa de secrets a injetar
secrets = {
    "TMDB_API_KEY": os.environ.get("TMDB_API_KEY", ""),
    "DRIVE_REFRESH_TOKEN": os.environ.get("DRIVE_REFRESH_TOKEN", ""),
    "DRIVE_CLIENT_ID": os.environ.get("DRIVE_CLIENT_ID", ""),
    "DRIVE_CLIENT_SECRET": os.environ.get("DRIVE_CLIENT_SECRET", ""),
    "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY", ""),
    "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", ""),
    "DEEPSEEK_API_KEY": os.environ.get("DEEPSEEK_API_KEY", ""),
    "AZURE_OPENAI_ENDPOINT": os.environ.get("AZURE_OPENAI_ENDPOINT", ""),
    "AZURE_OPENAI_API_KEY": os.environ.get("AZURE_OPENAI_API_KEY", ""),
    "AZURE_OPENAI_DEPLOYMENT": os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
}

replaced_count = 0

for cell in nb["cells"]:
    if cell["cell_type"] != "code":
        continue

    new_source = []
    for line in cell["source"]:
        for key, value in secrets.items():
            if not value: continue
            safe_val = json.dumps(value)
            old_line = line
            for fn in ["_ks", "_get", "_get_secret", "load_secret"]:
                line = line.replace(f'{fn}("{key}")', safe_val)
                line = line.replace(f"{fn}('{key}')", safe_val)
            if line != old_line:
                replaced_count += 1
        new_source.append(line)
    cell["source"] = new_source

with open(file_path, "w", encoding="utf-8") as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)

print(f"✅ {replaced_count} substituições de secrets realizadas no notebook com sucesso!")
