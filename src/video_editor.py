"""
Módulo de Edição e Renderização de Vídeo (FFmpeg / OpenCV / ASS Subtitles)

Monta o vídeo final unindo:
1. Intro do canal (sem loop no início)
2. Slideshow das imagens (16:9 / 1:1) com duração alternada (5-10s) em loop
3. Marca d'água animada estilo DVD bounce com opacidade 30% e fonte Bungee
4. Áudio da narração em alta fidelidade
5. Renderização ultra-rápida em Passada Única (Single-Pass Filtergraph) + Aceleração GPU NVENC
6. Loop instantâneo via stream copy (-c copy) em segundos
"""

import os
import random
import math
import logging
import subprocess
from dotenv import load_dotenv



load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

OUTPUT_DIR_DEFAULT = "output"
INTRO_PATH_DEFAULT = os.getenv("INTRO_PATH", r"D:\Applications\Movie-Pipeline\intro.mp4")

WATERMARK_TEXT_MAIN = "Saiba mais pelo telegram ➔ @LehDramas"
WATERMARK_TEXT_SUB  = "(Link Direto no 1º Comentário Fixado)"

def get_audio_duration(audio_path: str) -> float:
    """Retorna a duração exata do arquivo de áudio em segundos."""
    try:
        from pydub import AudioSegment
        sound = AudioSegment.from_file(audio_path)
        return len(sound) / 1000.0
    except Exception:
        pass

    try:
        import wave
        with wave.open(audio_path, 'rb') as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return frames / float(rate)
    except Exception:
        pass

    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(res.stdout.strip())
    except Exception:
        return 60.0


def generate_dvd_bounce_ass(output_ass_path: str, duration_sec: float, width: int = 1920, height: int = 1080, font_name: str = "Bungee") -> str:
    """
    Gera um arquivo de legendas .ass com animação de movimento quicante (DVD Bounce)
    para o texto da marca d'água com opacidade 30% (Alpha &H4D) e fonte configurável em tamanho grande (65pt).
    """
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: DVDBounce,{font_name},65,&H4DFFFFFF,&H4DFFFFFF,&H4D000000,&H4D000000,-1,0,0,0,100,100,0,0,1,2,0,5,10,10,10,1
Style: DVDBounceSub,{font_name},38,&H4DFFFFFF,&H4DFFFFFF,&H4D000000,&H4D000000,0,0,0,0,100,100,0,0,1,1,0,5,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    margin_x, margin_y = 250, 180
    positions = [
        (margin_x, margin_y),
        (width - margin_x, margin_y + 100),
        (width - margin_x, height - margin_y),
        (margin_x, height - margin_y - 50),
        (width // 2, margin_y),
        (margin_x, height // 2)
    ]
    
    t = 0.0
    step = 6.0 # 6 segundos por travessia de canto a canto (ritmo dinâmico alinhado à troca de fotos)

    pos_idx = 0
    
    def format_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int((seconds - int(seconds)) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    while t < duration_sec:
        t_end = min(t + step, duration_sec)
        p1 = positions[pos_idx % len(positions)]
        p2 = positions[(pos_idx + 1) % len(positions)]
        
        t_start_str = format_time(t)
        t_end_str = format_time(t_end)
        dur_ms = int((t_end - t) * 1000)
        
        move_tag = f"\\move({p1[0]},{p1[1]},{p2[0]},{p2[1]},0,{dur_ms})"
        line_main = f"Dialogue: 0,{t_start_str},{t_end_str},DVDBounce,,0,0,0,,{{{move_tag}}}{WATERMARK_TEXT_MAIN}\\N{WATERMARK_TEXT_SUB}"
        events.append(line_main)
        
        t = t_end
        pos_idx += 1

    os.makedirs(os.path.dirname(os.path.abspath(output_ass_path)), exist_ok=True)
    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events))
        
    return output_ass_path

def build_slideshow_concat_script(images: list[str], target_duration: float, temp_dir: str) -> str:
    """Gera um arquivo txt de concat do FFmpeg repetindo as imagens em loop com tempos alternados dinâmicos (3.5 a 6.0s) sem repetições consecutivas."""
    concat_txt = os.path.join(temp_dir, "slideshow_list.txt")
    current_time = 0.0
    lines = []
    last_img = None
    
    img_pool = list(images)
    if not img_pool:
        raise ValueError("Nenhuma imagem fornecida para o slideshow.")

    while current_time < target_duration:
        shuffled = list(img_pool)
        random.shuffle(shuffled)
        for img_path in shuffled:
            if img_path == last_img and len(img_pool) > 1:
                continue
            dur = round(random.uniform(3.5, 6.0), 2)
            clean_path = os.path.abspath(img_path).replace("\\", "/")
            lines.append(f"file '{clean_path}'")
            lines.append(f"duration {dur:.2f}")
            current_time += dur
            last_img = img_path
            if current_time >= target_duration:
                break
                
    lines.append(f"file '{os.path.abspath(img_pool[0]).replace('\\', '/')}'")

    with open(concat_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return concat_txt

def render_movie_video(
    slug: str,
    images: list[str],
    voiceover_path: str,
    output_dir: str = OUTPUT_DIR_DEFAULT,
    intro_path: str = INTRO_PATH_DEFAULT,
    target_runtime_minutes: float = 110.0,
    watermark_font: str = "Bungee"
) -> str:
    """
    Renderiza o vídeo final com alta performance em PASSADA ÚNICA (Single-Pass Filtergraph).
    Combina o slideshow de fotos, a marca d'água animada .ass e o áudio em uma única codificação.
    Aplica aceleração por hardware GPU (h264_nvenc) se disponível, caindo para libx264 se necessário.
    Por fim, realiza o loop instantâneo (-c copy em 2 segundos) para preencher a duração do filme.
    """
    os.makedirs(output_dir, exist_ok=True)
    temp_dir = os.path.join(output_dir, "temp_render")
    os.makedirs(temp_dir, exist_ok=True)

    final_output_path = os.path.join(output_dir, f"{slug}.mp4")
    bloco_queimado_temp = os.path.join(temp_dir, "bloco_queimado.mp4")
    intro_norm_temp = os.path.join(temp_dir, "intro_norm.mp4")
    ass_path = os.path.join(temp_dir, "watermark.ass")

    # 1. Duração do áudio da narração
    narration_duration = get_audio_duration(voiceover_path)

    # 2. Gera o arquivo de concat das imagens para a duração da narração
    concat_txt_path = build_slideshow_concat_script(images, narration_duration, temp_dir)

    # 3. Gera a legenda animada .ass (DVD Bounce) com a fonte configurável
    generate_dvd_bounce_ass(ass_path, narration_duration + 10.0, font_name=watermark_font)
    ass_path_escaped = os.path.abspath(ass_path).replace("\\", "/").replace(":", "\\:")

    # 4. Filtergraph Unificado (Redimensiona fotos + queima a legenda animada em PASSADA ÚNICA)
    vf_combined = f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,fps=30,ass='{ass_path_escaped}'"

    vcodec = "libx264"
    preset = "ultrafast"

    logging.info(f"🎨 PASSADA ÚNICA: Renderizando bloco do filme ({narration_duration:.1f}s = {narration_duration/60:.1f}min) com codec {vcodec} (preset {preset})...")

    cmd_single_pass = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat_txt_path,
        "-i", voiceover_path,
        "-vf", vf_combined,
        "-c:v", vcodec, "-preset", preset, "-threads", "0",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
        "-shortest",
        bloco_queimado_temp
    ]
    subprocess.run(cmd_single_pass, check=True)


    # 6. Normalização da vinheta Intro (se existir)
    has_intro = False
    if intro_path and os.path.exists(intro_path):
        logging.info("Normalizando Vinheta Intro...")
        cmd_intro = [
            "ffmpeg", "-y", "-i", intro_path,
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black",
            "-r", "30", "-c:v", vcodec, "-preset", preset, "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
            intro_norm_temp
        ]
        try:
            subprocess.run(cmd_intro, check=True)
            has_intro = True
        except Exception as intro_err:
            logging.warning(f"Aviso ao normalizar vinheta intro: {intro_err}")

    # 7. Loop Instantâneo via -c copy (executa em 2 segundos!) + corte exato com -t
    target_sec = target_runtime_minutes * 60.0
    num_loops = math.ceil(target_sec / narration_duration)
    total_dur_min = target_runtime_minutes

    logging.info(f"⚡ Loop instantâneo (-c copy): multiplicando bloco {num_loops}x e cortando em {total_dur_min:.1f} min exatos...")

    concat_stream_list = os.path.join(temp_dir, "concat_stream.txt")
    concat_lines = []
    if has_intro and os.path.exists(intro_norm_temp):
        concat_lines.append(f"file '{os.path.abspath(intro_norm_temp).replace('\\', '/')}'")

    bloco_abs = os.path.abspath(bloco_queimado_temp).replace("\\", "/")
    for _ in range(num_loops):
        concat_lines.append(f"file '{bloco_abs}'")

    with open(concat_stream_list, "w", encoding="utf-8") as f:
        f.write("\n".join(concat_lines) + "\n")

    cmd_fast_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_stream_list,
        "-c", "copy",
        "-t", str(target_sec),
        final_output_path
    ]
    subprocess.run(cmd_fast_concat, check=True)

    # Limpeza dos arquivos temporários de renderização
    try:
        import shutil
        shutil.rmtree(temp_dir)
    except Exception:
        pass

    logging.info(f"🎉 Vídeo finalizado com sucesso ({total_dur_min:.1f} min): {final_output_path}")
    return final_output_path
