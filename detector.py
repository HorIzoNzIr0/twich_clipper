import re, time, statistics
from collections import deque, Counter

LAUGH_CHARS = set("ахпвыеэмжсд")

LAUGH_WORDS = {"лол", "лул", "рофл", "ору", "ржу", "угар", "хы", "хех",
               "lol", "lul", "lulw", "omegalul", "rofl"}
WTF_WORDS = {"чел", "жесть", "бля"}
DEAD_WORDS = {"всё"}
DEAD_PHRASES = ["не могу", "я умер", "я сдох", "меня нет",
                "меня вынесло", "что это бля", "ну это всё"]


def squeeze(s):
    return re.sub(r"(.)\1+", r"\1", s)


def is_keyboard_laugh(w):
    letters = re.sub(r"[^а-яёa-z]", "", w)
    if len(letters) < 3 or letters.count("х") < 2:
        return False
    share = sum(c in LAUGH_CHARS for c in letters) / len(letters)
    return share >= 0.85


def token_category(raw):
    w = raw.lower()
    if re.fullmatch(r":?\){3,}", w):
        return "LAUGH"
    s = squeeze(w)
    if is_keyboard_laugh(w):
        return "LAUGH"
    if re.fullmatch(r"[xх][dд]", s) or re.fullmatch(r":[dд]", s):
        return "LAUGH"
    if s in LAUGH_WORDS:
        return "LAUGH"
    if s.startswith(("кекв", "kekw")) or s in ("кек", "kek"):
        return "KEK"
    if w.startswith("pog"):
        return "POG"
    if s in DEAD_WORDS:
        return "DEAD"
    if s in WTF_WORDS:
        return "WTF"
    return None


def classify(text):
    for w in text.split():
        cat = token_category(w)
        if cat:
            return cat, True
    low = squeeze(text.lower())
    if any(p in low for p in DEAD_PHRASES):
        return "DEAD", True
    letters = re.sub(r"[^А-Яа-яA-Za-z]", "", text)
    if len(letters) >= 5 and text.isupper():
        return "CAPS:" + low, True
    return low, False


class Detector:
    def __init__(self, window=10, min_score=30, z=3.0, cooldown=120,
                 warmup=90, min_hype_users=6, min_hype_share=0.3):
        self.window = window
        self.min_score = min_score          # минимальный скор окна
        self.z = z                          # насколько выше обычного уровня чата
        self.cooldown = cooldown            # пауза между клипами, сек
        self.warmup = warmup                # сколько сек изучаем чат до первого клипа
        self.min_hype_users = min_hype_users    # минимум РАЗНЫХ людей, которые реагируют
        self.min_hype_share = min_hype_share    # доля реакций среди всех сообщений окна
        self.msgs = deque()
        self.hist = deque(maxlen=600)
        self.last = 0
        self.top = ""
        self.hype_users = 0
        self.share = 0.0

    @property
    def warming(self):
        return len(self.hist) < self.warmup

    def on_message(self, user, text):
        key, hype = classify(text)
        self.msgs.append((time.time(), user, key, hype))

    def _score(self, now):
        while self.msgs and self.msgs[0][0] < now - self.window:
            self.msgs.popleft()
        users = {u for _, u, _, _ in self.msgs}
        hype_users = {u for _, u, _, h in self.msgs if h}
        keys = Counter(k for _, _, k, _ in self.msgs)
        same = max(keys.values(), default=0)

        self.hype_users = len(hype_users)
        hype_msgs = sum(1 for m in self.msgs if m[3])
        self.share = hype_msgs / len(self.msgs) if self.msgs else 0.0

        hype_keys = Counter(k for _, _, k, h in self.msgs if h)
        if hype_keys:
            k, n = hype_keys.most_common(1)[0]
            self.top = f"{k.split(':')[0]}x{n} люд={self.hype_users}"
        else:
            self.top = ""
        return len(self.msgs) + len(users) + 2 * len(hype_users) + same

    def tick(self):
        now = time.time()
        s = self._score(now)
        fire = False
        if not self.warming:
            mean = statistics.mean(self.hist)
            std = max(statistics.pstdev(self.hist), 3.0)   # нижняя граница, чтобы тихий чат не давал ложных срабатываний
            if (s >= self.min_score
                    and (s - mean) / std >= self.z
                    and self.hype_users >= self.min_hype_users
                    and self.share >= self.min_hype_share
                    and now - self.last > self.cooldown):
                self.last, fire = now, True
        self.hist.append(s)
        return fire, s


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "reakcii_russkogo_strim_chata.txt"
    miss = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or ord(line[0]) > 0x2000:
            continue
        if not classify(line)[1]:
            miss.append(line)
    print("не распознано:", miss or "всё распознано")