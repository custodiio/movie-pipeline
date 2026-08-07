# Mapa de Arquitetura do Projeto - Movie-Pipeline

## Visão Geral

Pipeline automatizado para seleção de filmes em alta (TMDB), geração de roteiro e review detalhada por IA através de cadeia estrita de fallbacks (`Azure OpenAI -> Gemini (4 modelos) -> DeepSeek -> OpenAI`), narração paralela em 2 blocos via Omni TTS com clonagem de voz, composição de vídeo estilo recap com slideshow dinâmico 16:9/1:1, marca d'água animada estilo DVD bounce e upload automatizado no Google Drive e YouTube.

## Componentes e Conexões

### 1. `.env` e Credenciais / Secrets

Armazena chaves de API e credenciais sensíveis (`TMDB_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `DRIVE_ACCESS_TOKEN`, `DRIVE_REFRESH_TOKEN`, `DRIVE_CLIENT_ID`, `DRIVE_CLIENT_SECRET`).

- Consumido por: `src/tmdb_client.py`, `src/movie_selector.py`, `src/image_downloader.py`, `src/drive_uploader.py`, `src/script_generator.py` e `src/omni_tts.py`.

### 2. Banco de Dados SQLite (`database.db`)

Tabela `movies`:

- `tmdb_id` (INTEGER PRIMARY KEY)
- `title` (TEXT NOT NULL)
- `original_title` (TEXT)
- `overview` (TEXT)
- `release_date` (TEXT)
- `runtime` (INTEGER)
- `status` (TEXT DEFAULT 'pending') - status possíveis: `'pending'`, `'selected'`, `'script_generated'`, `'video_rendered'`, `'posted'`
- `created_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
- `posted_at` (TIMESTAMP NULL)

- Gerenciado por: [src/database.py](file:///d:/Applications/Movie-Pipeline/src/database.py)

### 3. Módulos do Pipeline (Produção em VPS & Nuvem)

- **`src/tmdb_client.py`**:
  - Cliente HTTP para a API do TMDB (`/trending/movie/day` e `/movie/{id}`).
- **`src/movie_selector.py`**:
  - Função modular `get_next_unposted_movie(language="pt-BR") -> dict | None`.
  - Gera slug formatado (ex: `homem_aranha_2026`) e salva a resposta TXT contendo metadados.
- **`src/image_downloader.py`**:
  - Baixa de 30 a 150 imagens por filme.
  - Filtro estrito de proporção de aspecto (exclusivamente **16:9** ou no mínimo **1:1**, descartando **9:16** e **3:4**).
  - Possui fallback de scraper automatizado caso o TMDB não atinja 30 imagens.
- **`src/drive_uploader.py`**:
  - Gerencia o Google Drive (`Movie-Pipeline/Assets/` fixo e `Movie-Pipeline/Projetos/<slug>/`).
  - Executa limpeza de arquivos temporários de projetos anteriores, preservando `Assets/` (`intro.mp4` e `Clonagem/`).
- **`src/script_generator.py`**:
  - Solicita uma review/resumo extremamente detalhada por IA via cadeia estrita de fallbacks:
    `Azure OpenAI -> Gemini (gemini-3.5-flash, gemini-3.1-pro-preview, gemini-3.1-flash-lite, gemini-2.5-pro) -> DeepSeek -> OpenAI`.
  - Fracionado em 4 chamadas/atos para maximizar extensão e riqueza narrativa.
- **`src/omni_tts.py`**:
  - Busca o áudio de clonagem de voz em `Movie-Pipeline/Assets/Clonagem/` (ou Drive).
  - Síntese de voz em **2 blocos simultâneos** via `ThreadPoolExecutor` para dobrar a velocidade de narração nas portas OmniVoice (8001 e 8002).
- **`src/video_editor.py`**:
  - Renderizador automatizado via FFmpeg.
  - Adiciona Intro do canal (`intro.mp4`, toca 1 vez).
  - Slideshow com imagens em loop e durações alternadas (3-5s).
  - Marca d'água animada estilo DVD bounce com opacidade 30% e fonte Bungee.
  - Salva em `output/<slug>.mp4`.
- **`notebooks/movie_pipeline_master.ipynb`**:
  - Notebook mestre parametrizado contendo todas as células interativas totalmente preenchidas e prontas para execução no Kaggle/Colab.
- **`main.py`**:
  - Orquestrador principal da aplicação na VPS. Invoca as funções de cada etapa do pipeline em sequência.


