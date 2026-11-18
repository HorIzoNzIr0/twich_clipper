import subprocess, pathlib, threading, datetime as dt
from recorder import BUF, FFMPEG

CLIPS = pathlib.Path(__file__).parent / "clips"
CLIPS.mkdir(exist_ok=True)

WHISPER_MODEL = "small"   # "base" быстрее но хуже, "medium" лучше но медленнее
LANG = "ru"               # язык стрима; None = определять автоматически

_lock = threading.Lock()  # обрабатываем клипы по одному
_model = None


def get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        print("\n[sub] загружаю Whisper (первый раз качает модель, подожди)...")
        _model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    return _model


def ass_time(t):
    cs = int(round(max(t, 0) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


ASS_HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,86,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,2,2,60,60,430,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def make_ass(video, ass_path):
    """Whisper -> файл субтитров. Возвращает число фраз."""
    segments, _ = get_model().transcribe(
        str(video), language=LANG, word_timestamps=True, vad_filter=True)
    words = [w for seg in segments for w in (seg.words or [])]
    if not words:
        return 0

    # режем на куски по 3 слова или по паузе
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) >= 3 or w.start - cur[-1].end > 0.7):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)

    lines = []
    for i, ch in enumerate(chunks):
        start = ch[0].start
        end = ch[-1].end
        if i + 1 < len(chunks) and chunks[i + 1][0].start - end < 0.3:
            end = chunks[i + 1][0].start      # без мигания между фразами
        text = " ".join(w.word.strip() for w in ch).upper()
        text = text.replace("{", "").replace("}", "")
        lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end + 0.1)},Default,,0,0,0,,{text}")

    ass_path.write_text(ASS_HEAD + "\n".join(lines) + "\n", encoding="utf-8-sig")
    return len(chunks)


def render_vertical(raw, out, ass_name=None):
    """16:9 -> 9:16: видео по центру на размытом фоне + субтитры."""
    fc = ("[0:v]split=2[a][b];"
          "[a]scale=1080:1920:force_original_aspect_ratio=increase,"
          "crop=1080:1920,boxblur=30:5[bg];"
          "[b]scale=1080:-2[fg];"
          "[bg][fg]overlay=(W-w)/2:(H-h)/2[v]")
    last = "[v]"
    if ass_name:
        fc += f";[v]subtitles={ass_name}[out]"
        last = "[out]"
    cmd = [FFMPEG, "-loglevel", "error", "-y", "-i", str(raw),
           "-filter_complex", fc, "-map", last, "-map", "0:a?",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", str(out)]
    # cwd=CLIPS, чтобы в фильтре subtitles был простой путь без проблем с экранированием в Windows
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(CLIPS))


def make_clip(peak_ts, before=30, after=10):
    start, end = peak_ts - before, peak_ts + after
    segs = []
    for f in sorted(BUF.glob("*.ts")):
        try:
            t = dt.datetime.strptime(f.stem, "%Y%m%d-%H%M%S").timestamp()
        except ValueError:
            continue
        if start - 4 <= t <= end:
            segs.append(f.resolve())
    print(f"\n[clip] нашёл кусков: {len(segs)}")
    if not segs:
        print("[clip] в буфере пусто, клип не создан")
        return

    cid = int(peak_ts)
    lst = BUF / f"list-{cid}.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in segs))
    raw = CLIPS / f"raw-{cid}.mp4"
    r = subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-f", "concat",
                        "-safe", "0", "-i", str(lst), "-c", "copy", str(raw)],
                       capture_output=True, text=True)
    lst.unlink(missing_ok=True)
    if r.returncode != 0:
        print("[clip] ошибка нарезки:", r.stderr[-300:])
        return

    out = CLIPS / f"clip-{cid}.mp4"
    ass = CLIPS / f"sub-{cid}.ass"
    with _lock:
        try:
            print("[sub] распознаю речь...")
            n = make_ass(raw, ass)
            print(f"[sub] фраз: {n}")
            r = render_vertical(raw, out, ass.name if n else None)
            if r.returncode != 0 and n:
                print("[clip] субтитры не вшились:", r.stderr[-300:])
                print("[clip] делаю без субтитров")
                r = render_vertical(raw, out, None)
            if r.returncode != 0:
                print("[clip] ошибка рендера:", r.stderr[-300:])
                return
            print("CLIP:", out)
        except Exception as e:
            print("[clip] ошибка:", repr(e))
        finally:
            raw.unlink(missing_ok=True)
            ass.unlink(missing_ok=True)