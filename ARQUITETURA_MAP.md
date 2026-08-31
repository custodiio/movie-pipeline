# Mapa de Arquitetura do Projeto - Movie-Pipeline

## Visão Geral

Pipeline automatizado para seleção de filmes em alta (TMDB), geração de roteiro e review detalhada por IA através de cadeia estrita de fallbacks (`Azure OpenAI -> Gemini (gemini-3-7-flash / gemini-3.6-flash / gemini-3.5-flash / gemini-3.1-pro-preview / gemini-3.1-flash-lite / gemini-3-flash-preview / gemini-2.5-pro / gemini-2.5-flash / gemini-2.0-flash) -> DeepSeek -> OpenAI`), narração paralela em 2 blocos via Omni TTS com clonagem de voz, composição de vídeo estilo recap com slideshow dinâmico 16:9/1:1, marca d'água animada estilo DVD bounce e upload automatizado no Google Drive e YouTube.

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
  - Pré-padronização ultra-rápida de 100% das imagens via Pillow para Full HD 1920x1080 com ajuste de proporção elegante e centralização sobre fundo preto (zero tela preta, zero distorção para 16:9, 4:3 e 1:1).
  - Renderização do Bloco Visual Base com cada foto durando EXATAMENTE 5.00s e queima da marca d'água DVD bounce sincronizada em travessias de 5.0s sem congelamentos.
  - Multiplicação e mesclagem com a narração de áudio via Stream Copy instantâneo (`-c:v copy -c:a aac`) com corte preciso via `-shortest`.
  - Normalização da vinheta intro oficial e loop instantâneo final (`-c copy`) em segundos para cobrir a duração total do filme (110 min).
  - Salva em `output/<slug>.mp4`.


- **`src/kaggle_trigger.py`**:
  - Módulo para disparar a execução remota do notebook no Kaggle enviando um evento `repository_dispatch` para a API do GitHub Actions.
- **`inject_secrets.py`**:
  - Script que roda no GitHub Actions antes do `kaggle kernels push` para injetar com segurança as chaves de API (`AZURE_OPENAI`, `GEMINI`, `DEEPSEEK`, `OPENAI`, `DRIVE`) dentro do código do notebook.
- **`.github/workflows/run-notebook.yml`**:
  - Workflow automatizado do GitHub Actions que configura o Kaggle CLI, roda o `inject_secrets.py` e executa o `kaggle kernels push` com acelerador GPU Tesla T4.
- **`notebooks/movie_pipeline_master.ipynb`**:
  - Notebook mestre parametrizado com Célula 1b dedicada à subida dos Servidores OmniVoice (GPU0 + GPU1) e renderização NVENC ultra-rápida.
- **`src/sales_bot.py`**:
  - Bot dedicado de Vendas Automáticas via PIX SyncPay (`@telacheiafilmes_bot`).
  - Lida 100% via `.env` (sem nenhum valor padrão hardcodado), obtém dinamicamente o Nome real do usuário (`user.full_name`) e o Username do Telegram do cliente para o cadastro do PIX, configura a mensagem de saudação de boas-vindas exibida na tela antes de clicar em START (`set_my_description`), gera a chave PIX Copia e Cola instantaneamente no valor de R$ 10,00, exibe botões de **Suporte Humano** (`https://t.me/leh_lurdes`), monitora a confirmação do pagamento no banco a cada 10 segundos.
  - **Geração de Link Único & Auto-Revogação**: Gera dinamicamente um link de convite exclusivo por venda (`member_limit=1`, `expire_date=24h`) para o Canal VIP (`TELEGRAM_VIP_CHANNEL_ID`) usando a API oficial do Telegram com o Bot Admin autenticado. Assim que o cliente entra, o Telegram revoga o link automaticamente. Possui controle rigoroso de concorrência/idempotência (`DELIVERY_LOCK` + `record_sales_order`) para evitar envios duplicados, notificando o cliente e o administrador (`ADMIN_CHAT_ID`).
- **`src/syncpay_client.py`**:
  - Módulo cliente oficial da API SyncPay (`https://api.syncpayments.com.br`).
  - Sanitizado e limpo de qualquer dado pessoal ou telefone hardcodado. Gerencia a autenticação via Bearer Token com cache automático de 1h, solicitação de depósitos PIX Cash-In (`create_pix_cashin`) e consulta de status de transações (`check_transaction_status`).


- **`run_sales_bot.py`**:
  - Script principal na raiz para inicialização e execução contínua do Bot de Vendas `@telacheiafilmes_bot` em segundo plano.

- **`src/youtube_uploader.py`**:
  - Módulo de upload automático para o YouTube via API v3 (`google-api-python-client`).
  - Realiza o upload do vídeo final MP4 em partes resumable de 10 MB, aplicando o Título de Captura SEO (max 100 caracteres), a Descrição Adaptada, as Tags de alta busca, a Thumbnail 16:9 e o status de privacidade **Privado** (`privacyStatus="private"`).

- **`src/dailymotion_uploader.py`**:
  - Módulo de upload de alta velocidade para o **Dailymotion API v2**.
  - Autenticação OAuth 2.0 via `client_credentials` com o escopo `video.manage` e extração dinâmica do `profile_id` direto do token JWT.
  - **Adaptação Automática de Limites**: Se o vídeo ultrapassar 2 horas (120 min), realiza o corte instantâneo em ~1s com FFmpeg `-c copy` para `01:59:50`. Se o tamanho exceder 3.9 GB, comprime em alta velocidade para caber no limite oficial de 4.0 GB do Dailymotion.
  - Abertura de sessão em `POST /v2/files/upload_sessions`, upload streamado com chunking de 1 MB, medição de velocidade e callback de progresso em tempo real.
  - Publicação e vinculação sob o perfil do canal (`POST /v2/profiles/{profile_id}/videos`) com título, descrição, categoria (`tv`) e visibilidade pública.

- **`src/telegram_bot.py`**:
  - Módulo assíncrono do Bot Admin do Telegram (`@TelaCheiaadmin_bot`) para automação de postagens.
  - **Fluxo 1 (Canal Público `@dramasleh`)**: Busca filmes no TMDB por nome, inclui a pergunta interativa do formato de áudio (`STATE_SELECT_AUDIO`: `🔊 DUBLADO`, `💬 LEGENDADO` ou `🔊💬 DUBLADO / LEGENDADO`), filtra e organiza a galeria de imagens (Pôsteres PT, EN, Variadas), gera a Copy de Vendas com o layout padrão estrito e botão Inline `[🔒 Solicitar Acesso Vitalício R$10,00]` direcionado para o Bot de Vendas `@TelaCheiaFilmes_bot` (`https://t.me/TelaCheiaFilmes_bot?start=comprar_vip`) e o botão de Suporte (`@leh_lurdes`), enviando com preview e confirmação para o admin publicar no canal público.
  - **Fluxo 2 (Canal VIP)**: Publicação direta de mídia com suporte a canais protegidos (`noforwards=True`), links de canais privados (`t.me/...`) e Torrent magnets. Inclui submenu interativo para envio manual de arquivo de legendas (`.srt` / `.ass`), preservação de múltiplos áudios originais (Dublado/Inglês) e conversão ultra-rápida via Stream Copy (`-c copy`) para MP4 com `-movflags +faststart`. Garante extração de capa/thumbnail JPEG de alta resolução e duração de vídeo (`DocumentAttributeVideo`) para eliminar bugs de timestamp zerado (`00:00`).
  - **Fluxo 3 (Produzir Filme - Pipeline)**: Pesquisa o filme em alta no TMDB que ainda não foi postado e solicita confirmação do admin (`[✅ Confirmar Produção]` ou `[✏️ Definir Título Manualmente]`). Ao confirmar, realiza a limpeza completa dos arquivos temporários locais (`temp/` e `output/`) e no Google Drive (`Movie-Pipeline/Projetos/`), faz upload do arquivo de metadados (`.txt`), dispara o pipeline no Kaggle via GitHub Actions com GPU Tesla T4 e atualiza o status do banco SQLite para `'selected'` e posteriormente para `'concluido'` ao finalizar a renderização.
  - **Fluxo 4 (Gerador de Thumbnail 16:9 & Guia do YouTube)**: Permite a seleção de imagem de fundo 16:9 (via TMDB Backdrops ou envio manual no chat), aplicação da logo transparente do filme com proporção escalável (15% a 40%) e posicionamento em grid de 9 posições via Pillow (PIL). Conduz a geração do Guia de Postagem do YouTube contendo Título de Captura, Descrição Padrão formatada com elenco/diretor real, CTAs e Disclaimer fixo, e Tags de alta relevância separadas por vírgula, salvando `guia_postagem.txt`/`.json` e `thumbnail.png` no Google Drive.
  - **Fluxo 5 (Baixar Torrent Magnet p/ VIP)**: Permite o envio de qualquer link Magnet (`magnet:?xt=urn:btih:...`) via botão no menu ou comando (`/torrent`, `/magnet`), com opção de vincular arquivo de legenda `.srt`/`.ass` manual ou detecção automática de `.srt` na pasta baixada. Realiza o download em velocidade máxima via Aria2c com mais de 12 rastreadores públicos injetados, divide arquivos > 2GB/4GB instantaneamente com FFmpeg `-c copy` e realiza o upload para o Canal VIP via Telethon MTProto com barra de progresso, capa e duração exata.
  - **Fluxo 6 (Postar no YouTube)**: Publica vídeos no YouTube em modo Privado com Título SEO, Descrição, Tags e Thumbnail com acompanhamento de progresso em tempo real.
  - **Fluxo 7 (Postar no Dailymotion)**: Publica vídeos no Dailymotion via API v2 diretamente no canal oficial `x2dvwo7` (Tela Cheia Filmes) com upload streamado e acompanhamento de progresso e adaptação de limites em tempo real.
  - **Fluxo 8 (Postagem Simultânea YT + DM)**: Dispara simultaneamente os uploads para o YouTube e para o Dailymotion em paralelo (`asyncio.gather`), mantendo barra de progresso sincronizada para ambas as plataformas e fornecendo os dois links diretos ao final.


- **`inject_secrets.py`**:
  - Script que injeta as secrets do GitHub Actions (`TELEGRAM_BOT_TOKEN`, `ADMIN_CHAT_ID`, `TELEGRAM_VIP_CHANNEL_ID`, `TMDB_API_KEY`, etc.) diretamente no código do notebook master antes do disparo para o Kaggle.


- **`src/torrent_downloader.py`**:
  - Motor de download de Torrent de alta velocidade utilizando `Aria2c` portátil/nativo com injeção dinâmica dos melhores rastreadores públicos (`PUBLIC_TRACKERS`).
  - Suporta DHT, PEX, LPD e até 120 peers/conexões simultâneas com alocação rápida de arquivos no disco.
  - Inserção de legendas Softsub (`mov_text`) preservando 100% de faixas de áudio e vídeo originais com FFmpeg Stream Copy (`embed_subtitles_and_prepare_stream`).
  - Identificação e priorização automática de arquivos de vídeo (`.mkv`, `.mp4`, `.avi`, `.mov`, `.webm`, `.ts`, `.m4v`) e busca de legendas (`.srt`, `.ass`, `.vtt`).
  - Extração de metadados robustos (`duration`, `width`, `height`) e geração de miniatura JPEG de capa (`extract_video_metadata_and_thumb`).
  - Divisão instantânea de arquivos sem perda de qualidade via FFmpeg Stream Copy (`-c copy`) caso o vídeo ultrapasse o limite configurado (> 2GB / 4GB).

- **`src/fast_telethon.py`**:
  - Módulo de transferência de mídia em 32 partes concorrentes usando fila assíncrona (`asyncio.Queue`) e conexões MTProto paralelas (`_borrow_sender(dc_id)`). Acelera o download/upload de arquivos pesados (2GB+) de canais protegidos em até 20x, utilizando aceleração de hardware C/Rust `AES-NI` (`cryptg` / `tgcrypto`).

- **`run_bot.py`**:
  - Script principal na raiz para inicialização e execução contínua do Bot Admin do Telegram em segundo plano.

- **`main.py`**:
  - Orquestrador principal da aplicação na VPS. Invoca as funções de cada etapa do pipeline em sequência.




