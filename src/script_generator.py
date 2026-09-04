"""
Módulo de Geração de Roteiro/Review Detalhado por IA

Cadeia Estrita de Fallbacks:
1. Azure OpenAI
2. Gemini Models (gemini-3.5-flash -> gemini-3.1-pro-preview -> gemini-3.1-flash-lite -> gemini-2.5-pro)
3. DeepSeek API
4. OpenAI API (gpt-4o / gpt-4o-mini)
"""

import os
import time
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

AZURE_OPENAI_ENDPOINT   = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_KEY    = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

MODELS_GEMINI = [
    "gemini-3-7-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.0-flash"
]

def generate_llm_text(prompt: str, system_instruction: str = "") -> str:
    """
    Executa a geração de texto respeitando rigorosamente a cadeia de fallbacks:
    1. Azure OpenAI
    2. Gemini (gemini-3.5-flash, gemini-3.1-pro-preview, gemini-3.1-flash-lite, gemini-2.5-pro)
    3. DeepSeek API
    4. OpenAI API
    """
    errors = []

    # 1. Tentativa Azure OpenAI
    if AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT:
        try:
            logging.info("Tentando [1/4] Azure OpenAI...")
            from openai import OpenAI
            client_azure = OpenAI(base_url=AZURE_OPENAI_ENDPOINT, api_key=AZURE_OPENAI_API_KEY)
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})
            
            res = client_azure.chat.completions.create(
                model=AZURE_OPENAI_DEPLOYMENT,
                messages=messages,
                temperature=0.7
            )
            text = res.choices[0].message.content.strip()
            if text:
                logging.info("✔ Gerado via Azure OpenAI com sucesso!")
                return text
        except Exception as e:
            msg = f"Azure OpenAI falhou: {e}"
            logging.warning(f"  [FALLBACK] {msg}")
            errors.append(msg)

    # 2. Tentativa Gemini (Cadeia dos 4 modelos)
    if GEMINI_API_KEY:
        try:
            from google import genai
            client_gemini = genai.Client(api_key=GEMINI_API_KEY)
            for model_name in MODELS_GEMINI:
                try:
                    logging.info(f"Tentando [2/4] Gemini model: '{model_name}'...")
                    contents = f"{system_instruction}\n\n{prompt}" if system_instruction else prompt
                    response = client_gemini.models.generate_content(
                        model=model_name,
                        contents=contents
                    )
                    if response and response.text:
                        text = response.text.strip()
                        logging.info(f"✔ Gerado via Gemini ('{model_name}') com sucesso!")
                        return text
                except Exception as gemini_err:
                    msg = f"Gemini ({model_name}) falhou: {gemini_err}"
                    logging.warning(f"  [FALLBACK] {msg}")
                    errors.append(msg)
                    time.sleep(1)
        except Exception as e:
            msg = f"google-genai client erro: {e}"
            logging.warning(f"  [FALLBACK] {msg}")
            errors.append(msg)

    # 3. Tentativa DeepSeek
    if DEEPSEEK_API_KEY:
        try:
            logging.info("Tentando [3/4] DeepSeek API...")
            from openai import OpenAI
            client_ds = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})

            res = client_ds.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                temperature=0.7
            )
            text = res.choices[0].message.content.strip()
            if text:
                logging.info("✔ Gerado via DeepSeek API com sucesso!")
                return text
        except Exception as e:
            msg = f"DeepSeek API falhou: {e}"
            logging.warning(f"  [FALLBACK] {msg}")
            errors.append(msg)

    # 4. Tentativa OpenAI
    if OPENAI_API_KEY:
        try:
            logging.info("Tentando [4/4] OpenAI API (gpt-4o-mini)...")
            from openai import OpenAI
            client_oai = OpenAI(api_key=OPENAI_API_KEY)
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})

            res = client_oai.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.7
            )
            text = res.choices[0].message.content.strip()
            if text:
                logging.info("✔ Gerado via OpenAI API com sucesso!")
                return text
        except Exception as e:
            msg = f"OpenAI API falhou: {e}"
            logging.warning(f"  [FALLBACK] {msg}")
            errors.append(msg)

    raise RuntimeError(f"Todas as IAs da cadeia falharam! Detalhes: {'; '.join(errors)}")

def generate_detailed_movie_script(movie_info: dict) -> str:
    """
    Gera um roteiro/review completo e rico em detalhes para o filme em 4 requisições encadeadas:
    Parte 1: Introdução e Premissa
    Parte 2: Desenvolvimento da Trama e Atos 1 e 2
    Parte 3: Clímax e Pontos Chave
    Parte 4: Desfecho, Análise e Conclusão
    """
    title = movie_info.get("title", "")
    orig_title = movie_info.get("original_title", "")
    overview = movie_info.get("overview", "")
    genres = ", ".join(movie_info.get("genres", []))
    
    system_prompt = (
        "Você é o narrador oficial de um canal premium de resumos e reviews detalhadas de cinema. "
        "Sua missão é escrever um roteiro EXTREMAMENTE DETALHADO, MAJESTOSO E EXTENSO, descrevendo cena por cena com riqueza de detalhes, diálogos marcantes, contexto psicológico e tensão máxima. "
        "Seja o mais longo e detalhado possível. Não economize palavras nem resuma nada de forma rasa. Escreva textos longos, profundos e extremamente minuciosos. "
        "Não use marcações de áudio como '[som de suspense]' ou '(música sobe)'. Escreva apenas o texto corrido a ser narrado."
    )

    logging.info(f"Iniciando geração de roteiro por IA para '{title}' através da cadeia de fallbacks...")

    # Parte 1: Introdução
    p1 = f"Filme: {title} ({orig_title})\nGêneros: {genres}\nSinopse original: {overview}\n\nEscreva a PARTE 1 extremamente longa e minuciosa (Introdução envolvente, gancho inicial marcante, contexto profundo da história e apresentação completa dos protagonistas e do cenário)."
    part1 = generate_llm_text(p1, system_prompt)
    time.sleep(1)

    # Parte 2: Trama e Desenvolvimento
    p2 = f"Filme: {title}\nContinuação da Parte 1:\n{part1[-400:]}\n\nEscreva a PARTE 2 extremamente longa e detalhada (Desenvolvimento aprofundado da trama, arcos dos personagens, segredos revelados e construção do conflito central cena por cena)."
    part2 = generate_llm_text(p2, system_prompt)
    time.sleep(1)

    # Parte 3: Clímax
    p3 = f"Filme: {title}\nContinuação da Parte 2:\n{part2[-400:]}\n\nEscreva a PARTE 3 extremamente longa e intensa (Desenvolvimento do clímax, momentos de maior tensão, reviravoltas chocantes e sequências de impacto)."
    part3 = generate_llm_text(p3, system_prompt)
    time.sleep(1)

    # Parte 4: Desfecho e Veredito
    p4 = f"Filme: {title}\nContinuação da Parte 3:\n{part3[-400:]}\n\nEscreva a PARTE 4 extremamente completa (Conclusão emocionante, resolução de todos os arcos dos personagens, explicação das mensagens centrais e desfecho magistral)."
    part4 = generate_llm_text(p4, system_prompt)

    full_script = f"{part1}\n\n{part2}\n\n{part3}\n\n{part4}"
    logging.info(f"Roteiro completo gerado com sucesso para '{title}' ({len(full_script)} caracteres).")
    return full_script

def generate_sales_copy(movie_data: dict, audio_option: str = "DUBLADO") -> str:
    """
    Gera uma copy de vendas persuasiva com a estrutura padrão estrita solicitada pelo usuário:
    🍿 **NOME DO FILME**
    🔊 **OPÇÃO DE ÁUDIO**
    
    [sinopse emocionante]
    
    ----------------------------------------------------------
    💰 **Apenas R$ 10,00 (Pagamento Único)**
    ----------------------------------------------------------
    📌 O que você garante no acesso VIP: 
    🎬 Filme completo em alta definição (sem anúncios)
    📬 Download liberado para assistir offline
    ⚡️ Acesso vitalício e imediato ao canal privado

    👇 Clique abaixo para solicitar o acesso VIP:
    """
    title = movie_data.get("title", "Lançamento VIP").upper()
    overview = movie_data.get("overview", "")
    release_date = movie_data.get("release_date", "")
    year = release_date.split("-")[0] if release_date else ""
    
    prompt = f"""Você é um copywriter de elite para canais de cinema no Telegram.
Crie um resumo envolvente e emocionante de 2 a 4 linhas para a sinopse do filme abaixo:

Título: {title}
Ano: {year}
Sinopse original: {overview}

REGRAS DE RESPOSTA:
1. Retorne APENAS o parágrafo corrido da sinopse emocionante (2 a 4 linhas).
2. Não inclua título, marcações extras, explicações ou notas.
"""

    summary_text = generate_llm_text(prompt, system_instruction="Você é um Copywriter especialista em canais VIP de entretenimento.")
    if not summary_text or len(summary_text.strip()) < 10:
        summary_text = overview

    audio_formatted = audio_option.upper().strip()

    final_copy = (
        f"🍿 **{title}**\n"
        f"🔊 **{audio_formatted}**\n\n"
        f"{summary_text.strip()}\n\n"
        f"----------------------------------------------------------\n"
        f"💰 **Apenas R$ 10,00 (Pagamento Único)**\n"
        f"----------------------------------------------------------\n"
        f"📌 O que você garante no acesso VIP: \n"
        f"🎬 Filme completo em alta definição (sem anúncios)\n"
        f"📬 Download liberado para assistir offline\n"
        f"⚡️ Acesso vitalício e imediato ao canal privado\n\n"
        f"👇 Clique abaixo para solicitar o acesso VIP:"
    )

    return final_copy


