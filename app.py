import requests
import random
import time
from datetime import datetime
import pytz
from pystray import Icon, Menu, MenuItem
from PIL import Image, ImageDraw

url = "https://brreg-sok.onrender.com/"
norway_tz = pytz.timezone("Europe/Oslo")
running = True

def is_within_working_hours():
    now = datetime.now(norway_tz)
    return now.weekday() < 5 and (5, 30) <= (now.hour, now.minute) <= (17, 30)

def ping_website():
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            print(f"Ping vellykket: {datetime.now(norway_tz)}")
    except requests.RequestException:
        print("Ping feilet.")

def start_ping():
    global running
    while running:
        if is_within_working_hours():
            ping_website()
            interval = random.randint(3, 14) * 60
            time.sleep(interval)
        else:
            time.sleep(15 * 60)

def stop_program(icon, item):
    global running
    running = False
    icon.stop()

def create_icon_image():
    image = Image.new('RGB', (64, 64), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((16, 16, 48, 48), fill="blue")
    return image

menu = Menu(
    MenuItem('Stop', stop_program)
)

icon = Icon("PingBrreg", create_icon_image(), "Ping Brreg", menu)
icon.run(start_ping)
