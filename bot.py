import telebot
from telebot import types
import threading
import datetime
import json
import os

from xss_module import XSSScan

API_TOKEN = "7614878121:AAGVEnTLaHSbIW_AER8nutDVGplxllxXIHc"
bot = telebot.TeleBot(API_TOKEN)

ADMIN_USER_ID = 2082050164
FREE_LIMIT = 2
REQUIRED_CHANNEL = "Unknowns_cybergroup"
REFERRAL_REQUIRED = 4
MAX_TARGET_FILE_LINES = 20

LICENSE_FILE = "user_licenses.json"
USAGE_FILE = "usage_counts.json"
REFERRAL_FILE = "referrals.json"

user_licenses = {}
usage_counts = {}
referrals = {}
user_states = {}

STATE_AWAITING_LICENSE_USERID = 3
STATE_AWAITING_LICENSE_REMOVE_USERID = 4

def load_json(filename):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return json.load(f)
    return {}

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2, default=str)

def parse_expiry(lic):
    if "expiry" in lic and lic["expiry"]:
        lic["expiry"] = datetime.datetime.fromisoformat(lic["expiry"])
    if "last_reset" in lic and lic["last_reset"]:
        lic["last_reset"] = datetime.datetime.fromisoformat(lic["last_reset"])
    return lic

def load_data():
    global user_licenses, usage_counts, referrals
    user_licenses = load_json(LICENSE_FILE)
    usage_counts = load_json(USAGE_FILE)
    referrals = load_json(REFERRAL_FILE)
    for uid in user_licenses:
        user_licenses[uid] = parse_expiry(user_licenses[uid])

def save_data():
    save_json(LICENSE_FILE, user_licenses)
    save_json(USAGE_FILE, usage_counts)
    save_json(REFERRAL_FILE, referrals)

load_data()

def is_authorized(user_id):
    user_id_str = str(user_id)
    lic = user_licenses.get(user_id_str)
    if lic:
        if lic["type"] != "infinite":
            expiry = lic.get("expiry")
            if expiry and expiry < datetime.datetime.now():
                user_licenses.pop(user_id_str)
                save_data()
                return False
        return True
    return False

def can_use(user_id, requested_sites_count):
    user_id_str = str(user_id)
    if is_authorized(user_id):
        lic = user_licenses[user_id_str]
        if lic["type"] == "infinite":
            now = datetime.datetime.now()
            if "last_reset" not in lic or (now - lic["last_reset"]).days >= 1:
                lic["used_links_today"] = 0
                lic["last_reset"] = now
                save_data()
            if lic["used_links_today"] + requested_sites_count > 30:
                return False, 30 - lic["used_links_today"]
            else:
                return True, None
        else:
            return True, None
    else:
        current_count = usage_counts.get(user_id_str, 0)
        if current_count + requested_sites_count > FREE_LIMIT:
            return False, FREE_LIMIT - current_count
        return True, None

def update_usage(user_id, added_count):
    user_id_str = str(user_id)
    if is_authorized(user_id):
        lic = user_licenses[user_id_str]
        if lic["type"] == "infinite":
            lic["used_links_today"] += added_count
            save_data()
    else:
        usage_counts[user_id_str] = usage_counts.get(user_id_str, 0) + added_count
        save_data()

def send_usage_status(chat_id, user_id):
    if is_authorized(user_id):
        bot.send_message(chat_id, "شما لایسنس دارید و محدودیتی در استفاده ندارید.")
    else:
        used = usage_counts.get(str(user_id), 0)
        bot.send_message(chat_id, f"شما بدون لایسنس مجاز به اسکن {FREE_LIMIT} سایت هستید.\nتاکنون {used} سایت اسکن کرده‌اید.")

def check_membership(user_id):
    try:
        member = bot.get_chat_member(f"@{REQUIRED_CHANNEL}", user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if not check_membership(user_id):
        bot.send_message(chat_id, f"لطفاً ابتدا عضو کانال @{REQUIRED_CHANNEL} شوید تا بتوانید از ربات استفاده کنید.")
        return
    intro_text = (
        "سلام! من ربات اسکنر XSS هستم، وابسته به گروه سایبری Unkdowns.\n"
        "لینک‌ها را با فاصله بفرستید یا فایل target.txt ارسال کنید (هر خط یک سایت).\n"
        "توجه: بدون لایسنس فقط تا ۲ لینک می‌توانید اسکن کنید.\n"
        "در فایل target.txt حداکثر ۲۰ خط مجاز است و اگر بیشتر باشد، فقط ۲۰ خط اول پردازش می‌شود.\n"
        "هر ۴ رفرال، ۷ روز اشتراک رایگان دریافت می‌کنید.\n"
        "برای ارتباط با ادمین: @Unkdowns\n"
        "برای مشاهده تعداد استفاده /usage\n"
        "اگر لایسنس دارید /license\n"
    )
    bot.send_message(chat_id, intro_text)
    send_usage_status(chat_id, user_id)

@bot.message_handler(commands=['license'])
def cmd_license(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if is_authorized(user_id):
        bot.send_message(chat_id, "شما لایسنس دارید و می‌توانید به صورت نامحدود یا با محدودیت‌های لایسنس استفاده کنید.")
    else:
        bot.send_message(chat_id, "شما لایسنس ندارید. برای استفاده بیشتر نیاز به لایسنس دارید.")

@bot.message_handler(commands=['usage'])
def cmd_usage(message):
    send_usage_status(message.chat.id, message.from_user.id)

@bot.message_handler(commands=['referral'])
def cmd_referral(message):
    user_id = str(message.from_user.id)
    count = referrals.get(user_id, 0)
    bot.send_message(message.chat.id, f"شما تاکنون {count} رفرال دارید. با آوردن {REFERRAL_REQUIRED} رفرال، ۷ روز اشتراک رایگان می‌گیرید.")

@bot.message_handler(commands=['addreferral'])
def cmd_addreferral(message):
    if message.from_user.id != ADMIN_USER_ID:
        bot.send_message(message.chat.id, "شما دسترسی ادمین ندارید.")
        return
    bot.send_message(message.chat.id, "آیدی تلگرام کاربری که رفرال گرفته را بفرستید:")
    user_states[message.chat.id] = STATE_AWAITING_LICENSE_USERID

@bot.message_handler(commands=['removelicense'])
def cmd_removelicense(message):
    if message.from_user.id != ADMIN_USER_ID:
        bot.send_message(message.chat.id, "شما دسترسی ادمین ندارید.")
        return
    bot.send_message(message.chat.id, "آیدی تلگرام کاربری که می‌خواهید لایسنسش را حذف کنید بفرستید:")
    user_states[message.chat.id] = STATE_AWAITING_LICENSE_REMOVE_USERID

@bot.message_handler(func=lambda m: user_states.get(m.chat.id) == STATE_AWAITING_LICENSE_USERID)
def handle_add_referral(message):
    try:
        ref_user_id = message.text.strip()
        if not ref_user_id.isdigit():
            bot.send_message(message.chat.id, "آیدی نامعتبر است. لطفاً فقط عدد بفرستید.")
            return
        referrals[ref_user_id] = referrals.get(ref_user_id, 0) + 1
        save_data()
        bot.send_message(message.chat.id, f"رفرال به کاربر {ref_user_id} اضافه شد.")
        # اگر رفرال به حد نصاب رسید و کاربر لایسنس ندارد، 7 روز اشتراک رایگان بده
        if referrals[ref_user_id] >= REFERRAL_REQUIRED and not is_authorized(ref_user_id):
            expiry = datetime.datetime.now() + datetime.timedelta(days=7)
            user_licenses[ref_user_id] = {
                "type": "week",
                "expiry": expiry,
                "used_links_today": 0,
                "last_reset": datetime.datetime.now()
            }
            save_data()
            bot.send_message(int(ref_user_id), "شما به خاطر آوردن ۴ رفرال، ۷ روز اشتراک رایگان دریافت کردید.")
        user_states.pop(message.chat.id, None)
    except Exception as e:
        bot.send_message(message.chat.id, f"خطا: {str(e)}")
        user_states.pop(message.chat.id, None)

@bot.message_handler(func=lambda m: user_states.get(m.chat.id) == STATE_AWAITING_LICENSE_REMOVE_USERID)
def handle_remove_license(message):
    try:
        rem_user_id = message.text.strip()
        if not rem_user_id.isdigit():
            bot.send_message(message.chat.id, "آیدی نامعتبر است. لطفاً فقط عدد بفرستید.")
            return
        if rem_user_id in user_licenses:
            user_licenses.pop(rem_user_id)
            save_data()
            bot.send_message(message.chat.id, f"لایسنس کاربر {rem_user_id} حذف شد.")
            bot.send_message(int(rem_user_id), "لایسنس شما توسط ادمین حذف شد.")
        else:
            bot.send_message(message.chat.id, "این کاربر لایسنس ندارد.")
        user_states.pop(message.chat.id, None)
    except Exception as e:
        bot.send_message(message.chat.id, f"خطا: {str(e)}")
        user_states.pop(message.chat.id, None)

@bot.message_handler(commands=['contact'])
def cmd_contact(message):
    bot.send_message(message.chat.id, "برای ارتباط با ادمین، لطفاً به آیدی زیر پیام دهید:\n@Unkdowns")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text.strip()

    if not check_membership(user_id):
        bot.send_message(chat_id, f"لطفاً ابتدا عضو کانال @{REQUIRED_CHANNEL} شوید تا بتوانید از ربات استفاده کنید.")
        return

    urls = text.split()
    if len(urls) == 0:
        bot.send_message(chat_id, "لطفاً حداقل یک لینک برای اسکن ارسال کنید.")
        return

    can_use_flag, left = can_use(user_id, len(urls))
    if not can_use_flag:
        if left is not None and left <= 0:
            bot.send_message(chat_id, "شما به حد استفاده مجاز امروز رسیدید. لطفا فردا مجدد تلاش کنید یا لایسنس تهیه کنید.")
        else:
            bot.send_message(chat_id, f"شما فقط {left} لینک دیگر می‌توانید اسکن کنید.")
        return

    bot.send_message(chat_id, "اسکن شروع شد، لطفاً کمی صبر کنید...")
    threading.Thread(target=scan_and_send_result, args=(chat_id, urls, [])).start()

@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if not check_membership(user_id):
        bot.send_message(chat_id, f"لطفاً ابتدا عضو کانال @{REQUIRED_CHANNEL} شوید تا بتوانید از ربات استفاده کنید.")
        return

    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    filename = message.document.file_name

    if not filename.endswith(".txt"):
        bot.send_message(chat_id, "لطفاً فقط فایل متنی با پسوند .txt ارسال کنید.")
        return

    # خواندن خطوط فایل
    content = downloaded_file.decode("utf-8")
    lines = content.strip().split("\n")
    if len(lines) == 0:
        bot.send_message(chat_id, "فایل ارسال شده خالی است.")
        return

    # محدودیت تعداد خط ها
    lines = lines[:MAX_TARGET_FILE_LINES]

    # بررسی محدودیت تعداد لینک مجاز برای کاربر
    can_use_flag, left = can_use(user_id, len(lines))
    if not can_use_flag:
        if left is not None and left <= 0:
            bot.send_message(chat_id, "شما به حد استفاده مجاز امروز رسیدید. لطفاً فردا مجدد تلاش کنید یا لایسنس تهیه کنید.")
        else:
            bot.send_message(chat_id, f"شما فقط {left} لینک دیگر می‌توانید اسکن کنید.")
        return

    bot.send_message(chat_id, f"{len(lines)} لینک دریافت شد. اسکن شروع شد...")
    threading.Thread(target=scan_and_send_result, args=(chat_id, lines, [])).start()

def scan_and_send_result(chat_id, urls, cookies):
    try:
        results = []
        for url in urls:
            result = XSSScan.scan(url, cookies)
            results.append(f"[{url}]\n{result}\n{'='*40}")
        bot.send_message(chat_id, "\n\n".join(results))
        update_usage(chat_id, len(urls))
    except Exception as e:
        bot.send_message(chat_id, f"خطا در حین اسکن: {str(e)}")

# سرور Flask برای زنده نگه داشتن پروژه در Render
from flask import Flask
import threading

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running."

def run_flask():
    app.run(host="0.0.0.0", port=8080)

if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    print("ربات راه‌اندازی شد.")
    bot.infinity_polling()
