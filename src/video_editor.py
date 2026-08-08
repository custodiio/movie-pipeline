"""
Módulo de Edição e Renderização de Vídeo (FFmpeg / OpenCV / ASS Subtitles)

Monta o vídeo final unindo:
1. Intro do canal (sem loop no início)
2. Slideshow das imagens (16:9 / 1:1) com duração alternada (3-5s) e movimentos (Zoom In/Out, Pan) em loop
3. Marca d'água animada estilo DVD bounce com opacidade 30% e fonte Bungee
4. Áudio da narração + Trilha sonora em loop com ducking e fade-out
5. Nomenclatura final padronizada (<slug>.mp4)
"""

import os
import random
import math
import subprocess
import logging
from pydub import AudioSegment
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

INTRO_PATH = os.getenv("INTRO_PATH", r"D:\Applications\Movie-Pipeline\intro.mp4")

WATERMARK_TEXT_MAIN = "ASSISTA COMPLETO NO TELEGRAM ➔ @LehDramas"
WATERMARK_TEXT_SUB  = "(Link Direto no 1º Comentário Fixado)"

def get_audio_duration(audio_path: str) -> float:
    """Retorna a duração exata do arquivo de áudio em segundos."""
    try:
        sound = AudioSegment.from_file(audio_path)
        return len(sound) / 1000.0
    except Exception as e:
        logging.error(f"Erro ao medir duração do áudio: {e}")
        return 60.0

def generate_dvd_bounce_ass(output_ass_path: str, duration_sec: float, width: int = 1920, height: int = 1080) -> str:
    """
    Gera um arquivo de legendas .ass com animação de movimento quicante (DVD Bounce)
    para o texto da marca d'água com opacidade 30% (Alpha &H4D) e estilo Bungee.
    """
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: DVDBounce,Bungee,48,&H4DFFFFFF,&H4DFFFFFF,&H4D000000,&H4D000000,-1,0,0,0,100,100,0,0,1,2,0,5,10,10,10,1
Style: DVDBounceSub,Bungee,30,&H4DFFFFFF,&H4DFFFFFF,&H4D000000,&H4D000000,0,0,0,0,100,100,0,0,1,1,0,5,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    # Calcula posições quicantes (bounce) nas 4 pontas da tela ao longo do tempo
    events = []
    margin_x, margin_y = 200, 150
    positions = [
        (margin_x, margin_y),
        (width - margin_x, margin_y + 100),
        (width - margin_x, height - margin_y),
        (margin_x, height - margin_y - 50),
        (width // 2, margin_y),
        (margin_x, height // 2)
    ]
    
    t = 0.0
    step = 12.0 # MOVIMENTO LENTO DA WATERMARK: 12 segundos por travessia!

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
        
        # Tag \\move deve ficar no início do evento ASS uma única vez
        move_tag = f"\\move({p1[0]},{p1[1]},{p2[0]},{p2[1]})"
        line_main = f"Dialogue: 0,{t_start_str},{t_end_str},DVDBounce,,0,0,0,,{{{move_tag}}}{WATERMARK_TEXT_MAIN}\\N{WATERMARK_TEXT_SUB}"
        events.append(line_main)

        
        t = t_end
        pos_idx += 1

    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events))
        
    return output_ass_path

def build_slideshow_concat_script(images: list[str], target_duration: float, temp_dir: str) -> str:
    """Gera um arquivo txt de concat do FFmpeg repetindo as imagens em loop com tempos alternados (3 a 5s)."""
    concat_txt = os.path.join(temp_dir, "slideshow_list.txt")
    current_time = 0.0
    lines = []
    
    img_pool = list(images)
    if not img_pool:
        raise ValueError("Nenhuma imagem fornecida para o slideshow.")

    while current_time < target_duration:
        random.shuffle(img_pool)
        for img_path in img_pool:
            dur = random.uniform(5.0, 10.0)

            clean_path = os.path.abspath(img_path).replace("\\", "/")
            lines.append(f"file '{clean_path}'")
            lines.append(f"duration {dur:.2f}")
            current_time += dur
            if current_time >= target_duration:
                break
                
    # FFmpeg concat requer a última imagem repetida no final
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
    target_min_hours: float = 1.0
) -> str:
    """Renderiza o vídeo principal do filme (~11 min) e gera instantaneamente o vídeo longo (+1h) via stream loop (-c copy)."""
    os.makedirs(output_dir, exist_ok=True)
    temp_dir = os.path.join(output_dir, "temp_render")
    os.makedirs(temp_dir, exist_ok=True)

    final_output_path = os.path.join(output_dir, f"{slug}.mp4")
    slideshow_video_temp = os.path.join(temp_dir, "slideshow_temp.mp4")
    intro_norm_temp = os.path.join(temp_dir, "intro_norm.mp4")
    ass_path = os.path.join(temp_dir, "watermark.ass")

    # 1. Calcula duração do áudio da narração
    audio_seg = AudioSegment.from_file(voiceover_path)
    narration_duration = len(audio_seg) / 1000.0

    # 2. Gera/Garanta legenda ASS pré-calculada de 30 min (ultraleve)
    generate_dvd_bounce_ass(ass_path, 1800.0)

    # 3. Cria lista do Concat de Imagens
    concat_txt_path = build_slideshow_concat_script(images, narration_duration, temp_dir)

    slideshow_raw_temp = os.path.join(temp_dir, "slideshow_raw.mp4")

    # 4a. Passada 1: Renderiza o slideshow das fotos + áudio em vídeo contínuo
    vf_scale = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black"
    cmd_raw = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat_txt_path,
        "-i", voiceover_path,
        "-vf", vf_scale,
        "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
        "-shortest",
        slideshow_raw_temp
    ]
    logging.info(f"Renderizando base do filme ({narration_duration:.1f}s)...")
    subprocess.run(cmd_raw, check=True)

    # 4b. Passada 2: Aplica a marca d'água ASS sobre o vídeo contínuo (animação 100% fluida e sem resets)
    vf_ass = f"ass='{ass_path_escaped}'"
    cmd_watermark = [
        "ffmpeg", "-y",
        "-i", slideshow_raw_temp,
        "-vf", vf_ass,
        "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0",
        "-pix_fmt", "yuv420p", "-c:a", "copy",
        slideshow_video_temp
    ]
    logging.info("Aplicando Marca D'água animada em passada única contínua...")
    subprocess.run(cmd_watermark, check=True)


    # 4. Normaliza a Intro UMA ÚNICA VEZ para codificação idêntica
    has_intro = False
    if os.path.exists(intro_path):
        logging.info("Normalizando Vinheta Intro para padrão idêntico de stream...")
        cmd_intro = [
            "ffmpeg", "-y", "-i", intro_path,
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black",
            "-r", "30", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
            intro_norm_temp
        ]
        subprocess.run(cmd_intro, check=True)
        has_intro = True

    # 5. LOOP INSTANTÂNEO (-c copy) PARA CORRESPONDER À DURAÇÃO EXATA DO TÍTULO (Ex: 164 min)
    import math
    target_sec = target_min_hours * 3600.0 if target_min_hours > 5.0 else target_min_hours * 60.0
    num_loops = math.ceil(target_sec / narration_duration)
    total_dur_min = (narration_duration * num_loops) / 60.0

    logging.info(f"⚡ Gerando vídeo de {total_dur_min:.1f} minutos ({num_loops}x repetições de {narration_duration/60:.1f}min) para bater a duração do título ({target_sec/60:.0f} min) via concat -c copy...")

    
    concat_stream_list = os.path.join(temp_dir, "concat_stream.txt")
    concat_lines = []
    if has_intro and os.path.exists(intro_norm_temp):
        concat_lines.append(f"file '{os.path.abspath(intro_norm_temp).replace('\\\\', '/')}'")
    
    slide_abs = os.path.abspath(slideshow_video_temp).replace("\\", "/")
    for _ in range(num_loops):
        concat_lines.append(f"file '{slide_abs}'")

    with open(concat_stream_list, "w", encoding="utf-8") as f:
        f.write("\n".join(concat_lines) + "\n")

    cmd_fast_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_stream_list,
        "-c", "copy",
        final_output_path
    ]
    subprocess.run(cmd_fast_concat, check=True)

    # Limpeza dos arquivos temporários de renderização
    try:
        shutil.rmtree(temp_dir)
    except: pass

    logging.info(f"✨ Vídeo longo (+1h) finalizado com sucesso em: {final_output_path}")
    return final_output_path
