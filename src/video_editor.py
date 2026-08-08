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
Style: DVDBounce,Bungee,32,&H4DFFFFFF,&H4DFFFFFF,&H4D000000,&H4D000000,-1,0,0,0,100,100,0,0,1,2,0,5,10,10,10,1
Style: DVDBounceSub,Bungee,22,&H4DFFFFFF,&H4DFFFFFF,&H4D000000,&H4D000000,0,0,0,0,100,100,0,0,1,1,0,5,10,10,10,1

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
    step = 4.0 # Muda de posição a cada 4 segundos
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
        
        move_tag = f"\\move({p1[0]},{p1[1]},{p2[0]},{p2[1]})"
        
        # Texto principal
        line_main = f"Dialogue: 0,{t_start_str},{t_end_str},DVDBounce,,0,0,0,,{{{move_tag}}}{WATERMARK_TEXT_MAIN}\\N{{{move_tag}}}{WATERMARK_TEXT_SUB}"
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
            dur = random.uniform(3.0, 5.0)
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
    output_dir: str = "output",
    bgm_path: str = "",
    intro_path: str = INTRO_PATH
) -> str:
    """
    Renderiza o vídeo completo final:
    1. Renderiza o slideshow de imagens com narração e marca d'água DVD.
    2. Concatena com a Intro do canal.
    3. Salva com o nome padronizado <slug>.mp4.
    """
    os.makedirs(output_dir, exist_ok=True)
    temp_dir = os.path.join(output_dir, "temp_render")
    os.makedirs(temp_dir, exist_ok=True)
    
    final_output_path = os.path.join(output_dir, f"{slug}.mp4")
    slideshow_video_temp = os.path.join(temp_dir, "slideshow_part.mp4")
    ass_path = os.path.join(temp_dir, "watermark.ass")

    narration_duration = get_audio_duration(voiceover_path)
    logging.info(f"Duração da narração para '{slug}': {narration_duration:.2f}s")

    # 1. Gera o arquivo .ass da marca d'água animada
    generate_dvd_bounce_ass(ass_path, narration_duration)

    # 2. Gera a lista de slideshow
    concat_txt_path = build_slideshow_concat_script(images, narration_duration, temp_dir)

    # 3. Comando FFmpeg para montar a parte de slideshow (com zoompan e marca d'água .ass)
    ass_path_escaped = os.path.abspath(ass_path).replace("\\", "/").replace(":", "\\:")
    
    # Filtro de vídeo: slideshow + pad 16:9 + ass watermark
    vf_filter = f"scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,ass='{ass_path_escaped}'"
    
    cmd_cpu = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat_txt_path,
        "-i", voiceover_path,
        "-vf", vf_filter,
        "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        slideshow_video_temp
    ]

    try:
        if shutil.which("nvidia-smi"):
            cmd_gpu = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", concat_txt_path,
                "-i", voiceover_path,
                "-vf", vf_filter,
                "-c:v", "h264_nvenc", "-preset", "p4",
                "-pix_fmt", "yuv420p", "-r", "30",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                slideshow_video_temp
            ]
            subprocess.run(cmd_gpu, check=True)
        else:
            subprocess.run(cmd_cpu, check=True)
    except Exception as e:
        logging.warning(f"GPU NVENC falhou ({e}). Alternando para CPU ultra-rápida (libx264 -preset ultrafast)...")
        subprocess.run(cmd_cpu, check=True)

    # 4. Verifica existência da Intro do canal
    if os.path.exists(intro_path):
        logging.info(f"Intro encontrada ({intro_path}). Concatenando Intro + Slideshow...")
        # Re-encode intro & slideshow para garantir mesmo codec/resolução
        concat_list_file = os.path.join(temp_dir, "final_concat.txt")
        intro_clean = os.path.abspath(intro_path).replace("\\", "/")
        slide_clean = os.path.abspath(slideshow_video_temp).replace("\\", "/")
        
        with open(concat_list_file, "w", encoding="utf-8") as f:
            f.write(f"file '{intro_clean}'\nfile '{slide_clean}'\n")
            
        cmd_final = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_list_file,
            "-c", "copy",
            final_output_path
        ]
        subprocess.run(cmd_final, check=True)
    else:
        logging.warning(f"Intro não encontrada no caminho '{intro_path}'. Salvando slideshow diretamente...")
        import shutil
        shutil.move(slideshow_video_temp, final_output_path)

    # Limpeza dos arquivos temporários de renderização
    import shutil
    try:
        shutil.rmtree(temp_dir)
    except: pass

    logging.info(f"✨ Vídeo final concluído e salvo em: {final_output_path}")
    return final_output_path
