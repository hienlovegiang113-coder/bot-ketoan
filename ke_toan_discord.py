import discord
from discord.ext import commands, tasks
import os
import pytesseract, cv2, requests, re, sqlite3
import numpy as np
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
timers = []
countdown_message = None
last_embed_content = None

# ==============================
# DATABASE
# ==============================
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

    if countdown_message:
        return countdown_message

    channel = bot.get_channel(CHANNEL_COUNTDOWN)
    if not channel:
        return None

    async for msg in channel.history(limit=20):
        if msg.author == bot.user:
            countdown_message = msg
            return msg

    countdown_message = await channel.send("Đang khởi tạo bảng countdown...")
    return countdown_message

# ==============================
# UPDATE EMBED (ANTI 429)
# ==============================
async def update_embed():
    global last_embed_content

    msg = await get_countdown_message()
    if not msg:
        return

    now = datetime.now().timestamp()
    active_list = []

    for data in timers:
        remaining = int(data["end"] - now)
        if remaining > 0:
            active_list.append((data["name"], remaining, data["money"]))

    if not active_list:
        new_content = "Không có ai đang đếm giờ"
    else:
        active_list.sort(key=lambda x: x[1])
        desc = ""

        for name, remaining, money in active_list:
            h = remaining // 3600
            m = (remaining % 3600) // 60
            s = remaining % 60
            desc += f"**{name}** ➜ `{h:02}:{m:02}:{s:02}` | {money}k\n"

        new_content = desc

    if new_content == last_embed_content:
        return

    embed = discord.Embed(
        title="📊 BẢNG ĐẾM NGƯỢC",
        description=new_content,
        color=discord.Color.green()
    )

    try:
        await msg.edit(embed=embed)
        last_embed_content = new_content
    except:
        pass

# ==============================
# LOOP COUNTDOWN
# ==============================
@tasks.loop(seconds=5)
async def countdown_loop():
    now = datetime.now().timestamp()
    expired = []

    for t in timers[:]:
        if t["end"] <= now:
            expired.append(t)

    for t in expired:
        channel = bot.get_channel(CHANNEL_THUE_XE)
        if channel:
            await channel.send(f"🔔 {t['name']} đã hết giờ rồi!")
        timers.remove(t)

    if expired:
        await update_embed()

# ==============================
# OCR
# ==============================
def read_img(url):
    resp = requests.get(url)
    arr = np.asarray(bytearray(resp.content), dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2)
    text = pytesseract.image_to_string(gray, lang="eng+jpn+vie")
    return text

def detect_names(text):
    names = re.findall(r'[A-Z][a-zA-Z0-9_]{2,}', text)
    return list(set(names))

def extract_money(text):
    nums = re.findall(r'(\d+)k', text.lower())
    return sum(int(n) * 1000 for n in nums)

# ==============================
# MESSAGE EVENT
# ==============================
@bot.event
async def on_message(message):
    global daily_total

    if message.author.bot:
        return

    content = message.content.lower()

    # ===== NAME + TIME + MONEY =====
    match_full = re.search(r'(\w+)\s+(\d+h\d*p?|\d+h|\d+p)\s+(\d+)k', content)

    if match_full:
        name = match_full.group(1)
        time_str = match_full.group(2)
        money = match_full.group(3)

        hours = 0
        mins = 0

        h = re.search(r'(\d+)h', time_str)
        m = re.search(r'(\d+)p', time_str)

        if h:
            hours = int(h.group(1))
        if m:
            mins = int(m.group(1))

        total_seconds = hours * 3600 + mins * 60

        if total_seconds > 0:
            end_time = datetime.now().timestamp() + total_seconds

            timers.append({
                "name": name,
                "end": end_time,
                "money": money
            })

            await message.channel.send(f"⏰ Đã thêm {name} - {time_str} - {money}k")
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

    # ===== THUÊ XE (CỘNG TIỀN) =====
    if message.channel.id == CHANNEL_THUE_XE:
        money = extract_money(message.content)
        if money > 0:
            daily_total += money
            await message.channel.send(f"💰 +{money:,}đ")

    await bot.process_commands(message)

# ==============================
# !huygio
# ==============================
@bot.command()
async def huygio(ctx, name: str):
    removed = False

    for t in timers[:]:
        if t["name"].lower() == name.lower():
            timers.remove(t)
            removed = True

    if removed:
        await ctx.send(f"🗑 Đã xoá timer của {name}")
        await update_embed()
    else:
        await ctx.send("❌ Không tìm thấy tên")

# ==============================
# !doi
# ==============================
@bot.command()
async def doi(ctx, name1: str, name2: str):

    t1 = None
    t2 = None

    for t in timers:
        if t["name"].lower() == name1.lower():
            t1 = t
        if t["name"].lower() == name2.lower():
            t2 = t

    if not t1 or not t2:
        await ctx.send("❌ Không tìm thấy một trong hai tên")
        return

    t1["end"], t2["end"] = t2["end"], t1["end"]

    await ctx.send(f"🔄 Đã đổi giờ giữa {name1} và {name2}")
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
    print("🔥 BOT ONLINE FULL VERSION!!!")

    if not countdown_loop.is_running():
        countdown_loop.start()

    if not daily_report.is_running():
        daily_report.start()

    await update_embed()

bot.run(TOKEN)



