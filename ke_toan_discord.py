import discord
from discord.ext import commands, tasks
import os
import pytesseract, cv2, requests, re, sqlite3
import numpy as np
import asyncio
from datetime import datetime

pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

TOKEN = os.getenv("TOKEN")

CHANNEL_THUE_XE = 1439183974646681641
CHANNEL_CHOT_SO = 1439184035271151667
CHANNEL_BLACKLIST = 1462332169333772360
CHANNEL_COUNTDOWN = 1473627587912667209

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

daily_total = 0
timers = {}
countdown_message = None

# ===== DATABASE =====
conn = sqlite3.connect("data.db")
cur = conn.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS blacklist(name TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS loyal(name TEXT,count INTEGER)")
conn.commit()

# ==============================
# LẤY / TẠO MESSAGE COUNTDOWN
# ==============================
async def get_countdown_message():
    global countdown_message
    channel = bot.get_channel(CHANNEL_COUNTDOWN)

    if countdown_message:
        return countdown_message

    async for msg in channel.history(limit=20):
        if msg.author == bot.user:
            countdown_message = msg
            return msg

    countdown_message = await channel.send("Đang khởi tạo bảng countdown...")
    return countdown_message

# ==============================
# UPDATE EMBED
# ==============================
async def update_embed():
    msg = await get_countdown_message()

    embed = discord.Embed(
        title="📊 BẢNG ĐẾM NGƯỢC",
        color=discord.Color.green()
    )

    if not timers:
        embed.description = "Không có ai đang đếm giờ"
    else:
        sorted_timers = sorted(
            timers.items(),
            key=lambda x: x[1] - datetime.now().timestamp()
        )

        desc = ""
        for name, end_time in sorted_timers:
            remaining = int(end_time - datetime.now().timestamp())

            if remaining <= 0:
                continue

            h = remaining // 3600
            m = (remaining % 3600) // 60
            s = remaining % 60

            desc += f"**{name}** ➜ `{h:02}:{m:02}:{s:02}`\n"

        embed.description = desc if desc else "Không có ai đang đếm giờ"

    await msg.edit(embed=embed)

# ==============================
# LOOP UPDATE 5s
# ==============================
@tasks.loop(seconds=5)
async def countdown_loop():
    to_remove = []

    for name, end_time in timers.items():
        if int(end_time - datetime.now().timestamp()) <= 0:
            to_remove.append(name)

    for name in to_remove:
        del timers[name]

    await update_embed()

# ==============================
# OCR
# ==============================
def read_img(url):
    resp = requests.get(url)
    arr = np.asarray(bytearray(resp.content), dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray,None,fx=2,fy=2)
    text = pytesseract.image_to_string(gray, lang="eng+jpn+vie")
    return text

def detect_names(text):
    names = re.findall(r'[A-Z][a-zA-Z0-9_]{2,}', text)
    return list(set(names))

def extract_money(text):
    nums = re.findall(r'(\d+)k', text.lower())
    return sum(int(n)*1000 for n in nums)

# ==============================
# MESSAGE EVENT
# ==============================
@bot.event
async def on_message(message):
    global daily_total

    if message.author.bot:
        return

    msg = message.content.lower().replace(" ", "")

    # ===== TIMER =====
    match = re.search(r'(\d+h\d+p|\d+h|\d+p)', msg)

    if match:
        time_str = match.group()

        hours = 0
        mins = 0

        h = re.search(r'(\d+)h', time_str)
        m = re.search(r'(\d+)p', time_str)

        if h:
            hours = int(h.group(1))
        if m:
            mins = int(m.group(1))

        total_seconds = hours*3600 + mins*60

        if total_seconds > 0:
            name = message.author.display_name
            end_time = datetime.now().timestamp() + total_seconds
            timers[name] = end_time

            await message.channel.send(f"⏰ {name} đã đặt {time_str}")
            await update_embed()

    # ===== BLACKLIST =====
    if message.channel.id == CHANNEL_BLACKLIST:
        for att in message.attachments:
            text = read_img(att.url)
            names = detect_names(text)
            for name in names:
                cur.execute("INSERT INTO blacklist VALUES(?)",(name,))
                conn.commit()
                await message.channel.send(f"⛔ Đã lưu blacklist: {name}")

    # ===== THUÊ XE =====
    if message.channel.id == CHANNEL_THUE_XE:
        money = extract_money(message.content)
        if money > 0:
            daily_total += money
            await message.channel.send(f"💰 +{money:,}đ")

    await bot.process_commands(message)

# ==============================
# !doi user1 user2
# ==============================
@bot.command()
async def doi(ctx, user1: str, user2: str):

    key1 = None
    key2 = None

    for name in timers.keys():
        if name.lower() == user1.lower():
            key1 = name
        if name.lower() == user2.lower():
            key2 = name

    if not key1 or not key2:
        await ctx.send("❌ Một trong hai người không có giờ")
        return

    timers[key1], timers[key2] = timers[key2], timers[key1]

    await ctx.send(f"🔄 Đã đổi giờ giữa {key1} và {key2}")
    await update_embed()

# ==============================
# !huygio
# ==============================
@bot.command()
async def huygio(ctx):
    name = ctx.author.display_name

    if name not in timers:
        await ctx.send("❌ Bạn không có giờ để hủy")
        return

    del timers[name]
    await ctx.send("🗑 Đã hủy giờ của bạn")
    await update_embed()

# ==============================
# CHỐT SỔ NGÀY
# ==============================
@tasks.loop(minutes=1)
async def daily_report():
    global daily_total
    now = datetime.now()

    if now.hour == 0 and now.minute == 0:
        ch = bot.get_channel(CHANNEL_CHOT_SO)
        if ch:
            await ch.send(f"📊 TỔNG THU HÔM NAY: {daily_total:,}")
        daily_total = 0

# ==============================
# READY
# ==============================
@bot.event
async def on_ready():
    print("🔥 BOT ONLINE!!!")
    countdown_loop.start()
    daily_report.start()

bot.run(TOKEN)














