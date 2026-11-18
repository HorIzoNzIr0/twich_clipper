import asyncio, re, ssl

LINE = re.compile(r"^(?:@\S+ )?:(\w+)!\S+ PRIVMSG #\S+ :(.*)$")

async def read_chat(channel, on_message):
    channel = channel.lower().lstrip("#")
    ctx = ssl.create_default_context()
    while True:
        try:
            print(f"\n[chat] подключаюсь к #{channel}...")
            reader, writer = await asyncio.open_connection(
                "irc.chat.twitch.tv", 6697, ssl=ctx)
            writer.write(b"PASS SCHMOOPIIE\r\n")
            writer.write(b"NICK justinfan12345\r\n")
            writer.write(f"JOIN #{channel}\r\n".encode())
            await writer.drain()
            shown = 0
            while True:
                raw = await reader.readline()
                if not raw:
                    print("\n[chat] соединение закрыто")
                    break
                line = raw.decode(errors="ignore").strip()
                if line.startswith("PING"):
                    writer.write(b"PONG :tmi.twitch.tv\r\n")
                    await writer.drain()
                elif "PRIVMSG" in line:
                    m = LINE.match(line)
                    if m:
                        on_message(m.group(1), m.group(2))
                        if shown < 5:
                            shown += 1
                            print(f"\n[chat] {m.group(1)}: {m.group(2)[:60]}")
                else:
                    print("\n[chat]", line[:100])
        except Exception as e:
            print("\n[chat] ошибка:", repr(e))
        await asyncio.sleep(3)