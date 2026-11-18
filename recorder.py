import subprocess, sys, time, pathlib
import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

BASE = pathlib.Path(__file__).parent
BUF = BASE / "buffer"
BUF.mkdir(exist_ok=True)

QUALITY = "1080p60,1080p,best"   # если 1080 нет, возьмёт лучшее из доступного


def start_recorder(channel):
    sl = subprocess.Popen(
        [sys.executable, "-m", "streamlink", "--stdout",
         f"twitch.tv/{channel}", QUALITY],
        stdout=subprocess.PIPE,
    )
    ff = subprocess.Popen(
        [FFMPEG, "-loglevel", "error", "-i", "pipe:0", "-c", "copy",
         "-f", "segment", "-segment_time", "4", "-reset_timestamps", "1",
         "-strftime", "1", str(BUF / "%Y%m%d-%H%M%S.ts")],
        stdin=sl.stdout,
    )
    return sl, ff


def cleanup(keep_sec=100):
    for f in BUF.glob("*.ts"):
        try:
            if time.time() - f.stat().st_mtime > keep_sec:
                f.unlink()
        except OSError:
            pass