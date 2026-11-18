import asyncio, sys, time, subprocess, atexit, signal, os
from chat import read_chat
from recorder import start_recorder, cleanup, BUF
from clipper import make_clip
from detector import Detector

BEFORE = 30     # сколько секунд ДО пика брать в клип
AFTER = 10      # сколько секунд ПОСЛЕ пика
procs = []


def kill_all():
    for p in procs:
        try:
            if p.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)],
                                   capture_output=True)
                else:
                    p.kill()
        except Exception:
            pass
    procs.clear()


atexit.register(kill_all)


def _on_signal(*_):
    kill_all()
    raise KeyboardInterrupt


for name in ("SIGBREAK", "SIGTERM"):
    if hasattr(signal, name):
        signal.signal(getattr(signal, name), _on_signal)


async def delayed_clip(peak):
    await asyncio.sleep(AFTER + 6)
    await asyncio.to_thread(make_clip, peak, BEFORE, AFTER)


async def main(channel):
    channel = channel.lower().lstrip("#")

    r = subprocess.run([sys.executable, "-m", "streamlink", f"twitch.tv/{channel}"],
                       capture_output=True, text=True)
    if "Available streams" not in (r.stdout + r.stderr):
        print(f"\n❌ {channel} сейчас не в эфире (или имя неверное). Выбери другого стримера.")
        return

    for f in BUF.glob("*.ts"):
        try:
            f.unlink()
        except OSError:
            pass

    # НАСТРОЙКИ ЧУВСТВИТЕЛЬНОСТИ (читай подсказку внизу ответа)
    det = Detector(
        min_score=30,        # минимальный скор окна в 10 сек
        z=3.0,               # во сколько раз "всплеск" выше обычного уровня чата
        cooldown=120,        # пауза между клипами, сек
        warmup=90,           # первые N сек только изучаем чат
        min_hype_users=6,    # минимум РАЗНЫХ людей, которые смеются/реагируют
        min_hype_share=0.3,  # доля реакций среди сообщений окна
    )

    sl, ff = start_recorder(channel)
    procs.extend([sl, ff])

    chat_task = asyncio.create_task(read_chat(channel, det.on_message))
    clip_tasks = set()
    n = 0
    try:
        while True:
            await asyncio.sleep(1)
            n += 1

            if sl.poll() is not None or ff.poll() is not None:
                print("\nСтрим закончился или запись упала. Выхожу.")
                break

            if n % 30 == 0:
                cleanup()

            fire, score = det.tick()
            mark = " (прогрев)" if det.warming else ""
            print(f"score={score} {det.top}{mark}          ", end="\r")
            if fire:
                print(f"\n🔥 момент! score={score} {det.top}")
                t = asyncio.create_task(delayed_clip(time.time()))
                clip_tasks.add(t)
                t.add_done_callback(clip_tasks.discard)
    finally:
        chat_task.cancel()
        kill_all()


if __name__ == "__main__":
    try:
        channel = sys.argv[1] if len(sys.argv) > 1 else input("Имя стримера: ").strip()
        asyncio.run(main(channel))
    except KeyboardInterrupt:
        print("\nОстановлено")