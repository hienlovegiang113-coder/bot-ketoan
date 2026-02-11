import discord
from discord.ext import commands, tasks
import os
import pytesseract, cv2, requests, re, sqlite3
import numpy as np
import asyncio
import re
from datetime import datetime

pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

TOKEN = os.getenv("TOKEN")

CHANNEL_THUE_XE = 1439183974646681641
CHANNEL_CHOT_SO = 1439184035271151667
CHANNEL_BLACKLIST = 1462332169333772360

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

daily_total = 0

# ===== database =====
conn = sqlite3.connect("data.db")
cur = conn.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS blacklist(name TEXT)")
cur.execute("CREATE TABLE IF NOT EXISTS loyal(name TEXT,count INTEGER)")
conn.commit()

# ===== OCR =====
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

# ===== MESSAGE =====
@bot.event
async def on_message(message):
    global daily_total

    if message.author.bot:
        return
        
# ===== HẸN GIỜ ĐẾM NGƯỢC =====
import asyncio, re

msg = message.content.lower().replace(" ", "")

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
        name = message.content.split()[0]

        await message.channel.send(f"⏰ {name} đã đặt giờ {time_str}")

        async def timer():
            await asyncio.sleep(total_seconds)
            await message.channel.send(f"🚨 HẾT GIỜ {name} - {message.content}")

        bot.loop.create_task(timer())
        
    # ==============================
    # BLACKLIST CHANNEL
    # ==============================
    if message.channel.id == CHANNEL_BLACKLIST:
        for att in message.attachments:
            text = read_img(att.url)
            names = detect_names(text)

            for name in names:
                cur.execute("INSERT INTO blacklist VALUES(?)",(name,))
                conn.commit()
                await message.channel.send(f"⛔ Đã lưu blacklist: {name}")

    # ==============================
    # THUÊ XE CHANNEL
    # ==============================
    if message.channel.id == CHANNEL_THUE_XE:

        # đọc tiền text
        money = extract_money(message.content)
        if money > 0:
            daily_total += money
            await message.channel.send(f"💰 +{money:,}đ")

        # đọc ảnh
        for att in message.attachments:
            text = read_img(att.url)

            money_img = extract_money(text)
            if money_img > 0:
                daily_total += money_img
                await message.channel.send(f"💰 +{money_img:,}đ")

            names = detect_names(text)

            for name in names:
                cur.execute("SELECT name FROM blacklist WHERE name=?",(name,))
                if cur.fetchone():
                    await message.channel.send(f"🚨 BLACKLIST: {name}")

                cur.execute("SELECT count FROM loyal WHERE name=?",(name,))
                row = cur.fetchone()

                if row:
                    new = row[0] + 1
                    cur.execute("UPDATE loyal SET count=? WHERE name=?",(new,name))
                else:
                    new = 1
                    cur.execute("INSERT INTO loyal VALUES(?,?)",(name,1))

                conn.commit()

                if new == 5:
                    await message.channel.send(f"🌟 KHÁCH THÂN: {name} (5 lần)")
                if new > 5:
                    await message.channel.send(f"💎 {name} đã thuê {new} lần")

    await bot.process_commands(message)
# ==============================
# CHỐT SỔ NGÀY
# ==============================
@tasks.loop(minutes=1)
async def daily_report():
    global daily_total
    now = datetime.now()

    if now.hour==0 and now.minute==0:
        ch = bot.get_channel(CHANNEL_CHOT_SO)
        if ch:
            await ch.send(f"📊 TỔNG THU HÔM NAY: {daily_total:,}")
        daily_total=0
@bot.event
async def on_ready():
    print("🔥 BOT ONLINE!!!")
    daily_report.start()
bot.run(TOKEN)















