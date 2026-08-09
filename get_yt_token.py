"""
Script Utilitário para Autenticação do YouTube & Google Drive
Gera o YOUTUBE_REFRESH_TOKEN com permissões de upload no YouTube e acesso ao Drive.
"""
import os
import sys
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

client_id = os.getenv("YOUTUBE_CLIENT_ID") or os.getenv("DRIVE_CLIENT_ID")
client_secret = os.getenv("YOUTUBE_CLIENT_SECRET") or os.getenv("DRIVE_CLIENT_SECRET")

print("=" * 60)
print("🔑 AUTENTICAÇÃO DO YOUTUBE DATA API v3 (MARIA DE LURDES)")
print("=" * 60)

params = {
    "client_id": client_id,
    "redirect_uri": "https://developers.google.com/oauthplayground",
    "response_type": "code",
    "scope": "https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/youtube.upload",
    "access_type": "offline",
    "prompt": "consent"
}

auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)

print("\n1. Abra o link abaixo no seu navegador (com a conta mariadelurdesalvesdoprado@gmail.com):")
print(auth_url)
print("\n2. Clique em 'Permitir' para dar acesso de Upload no YouTube.")
print("3. Você será redirecionado para o OAuth Playground do Google.")
print("4. Copie o código 'code=...' da URL ou da tela e cole abaixo:")

code = input("\n👉 Cole o Código de Autorização aqui: ").strip()

if code:
    import requests
    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": "https://developers.google.com/oauthplayground",
        "grant_type": "authorization_code"
    }
    r = requests.post(token_url, data=payload)
    data = r.json()
    refresh_token = data.get("refresh_token")
    if refresh_token:
        print("\n🎉 NOVO REFRESH TOKEN GERADO COM SUCESSO!")
        print(f"YOUTUBE_REFRESH_TOKEN={refresh_token}")
        
        # Atualiza o arquivo .env
        env_lines = []
        if os.path.exists(".env"):
            with open(".env", "r", encoding="utf-8") as f:
                env_lines = f.readlines()
        
        new_lines = []
        updated = False
        for line in env_lines:
            if line.startswith("YOUTUBE_REFRESH_TOKEN="):
                new_lines.append(f"YOUTUBE_REFRESH_TOKEN={refresh_token}\n")
                updated = True
            else:
                new_lines.append(line)
        if not updated:
            new_lines.append(f"\nYOUTUBE_REFRESH_TOKEN={refresh_token}\n")
            
        with open(".env", "w", encoding="utf-8") as f:
            f.writelines(new_lines)
            
        print("✅ Variável YOUTUBE_REFRESH_TOKEN atualizada no seu arquivo .env!")
    else:
        print("❌ Erro ao obter refresh token:", data)
