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
  - Geração de roteiro/review cinematográfico ultra-detalhado e extenso em 4 partes através de IA.
  - Prompts aprofundados exigindo riqueza de detalhes de cena por cena, motivações psicológicas, diálogos marcantes e texto muito mais longo.
  - Cadeia estrita de fallbacks: Azure OpenAI (`gpt-5-mini`) -> Gemini (3.5-flash / 3.1-pro / 3.1-flash-lite / 2.5-pro) -> DeepSeek -> OpenAI (`gpt-5-mini`).
- **`src/omni_tts.py`**:
  - Módulo de síntese de voz paralela em 2 blocos utilizando os servidores OmniVoice (`http://127.0.0.1:8001/` e `http://127.0.0.1:8002/`) com o áudio de clonagem de referência em `Assets/Clonagem/`.
- **`src/video_editor.py`**:
  - Renderizador de vídeo no FFmpeg com aceleração por hardware GPU Nvidia NVENC (`h264_nvenc`) a 250+ FPS ou CPU ultra-rápida.
  - Concatenação com a vinheta oficial `intro.mp4`.
  - Slideshow ultra-estável com durações de 5.0s a 10.0s por imagem perfeitamente sincronizadas com o áudio da narração.
  - Marca d'água animada estilo DVD bounce com `\move` ASS legível, gigante (65pt Bungee) e lenta (12s por travessia), com coordenadas e milissegundos explícitos `\move(x1,y1,x2,y2,0,12000)`.
  - Renderização otimizada em 3 etapas ultra-rápidas (Passo 1: Concatena slideshow base puro de fotos para o tempo da narração; Passo 2: Renderiza e queima a legenda ASS 65pt + áudio da narração no bloco do filme em 1 única passada; Passo 3: Concatena vinheta intro + repetições do bloco queimado via stream copy `-c copy` instantâneo em 2 segundos para atingir a duração total do TXT).
  - Salva em `output/<slug>.mp4`.


- **`src/kaggle_trigger.py`**:
  - Módulo para disparar a execução remota do notebook no Kaggle enviando um evento `repository_dispatch` para a API do GitHub Actions.
- **`inject_secrets.py`**:
  - Script que roda no GitHub Actions antes do `kaggle kernels push` para injetar com segurança as chaves de API (`AZURE_OPENAI`, `GEMINI`, `DEEPSEEK`, `OPENAI`, `DRIVE`) dentro do código do notebook.
- **`.github/workflows/run-notebook.yml`**:
  - Workflow automatizado do GitHub Actions que configura o Kaggle CLI, roda o `inject_secrets.py` e executa o `kaggle kernels push` com acelerador GPU Tesla T4.
- **`notebooks/movie_pipeline_master.ipynb`**:
  - Notebook mestre parametrizado com Célula 1b dedicada à subida dos Servidores OmniVoice (GPU0 + GPU1) e renderização NVENC ultra-rápida.
- **`main.py`**:
  - Orquestrador principal da aplicação na VPS. Invoca as funções de cada etapa do pipeline em sequência.



