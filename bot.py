
import telebot
from telebot import types
import threading
from xss_module import XSSScan  # فرض می‌کنیم فایل xss_module.py کنار این فایل هست و کلاس XSSScan تعریف شده
import time

API_TOKEN = "7614878121:AAGVEnTLaHSbIW_AER8nutDVGplxllxXIHc"
bot = telebot.TeleBot(API_TOKEN)

# تنظیمات ادمین و لایسنس
ADMIN_USER_ID = 2082050164  # آیدی تلگرام خودت اینجا بذار
licenses = set()  # user_id هایی که لایسنس دارند به صورت رشته ذخیره میشن
usage_counts = {}  # user_id : تعداد سایت اسکن شده (برای کاربران بدون لایسنس)
FREE_LIMIT = 2

def is_authorized(user_id):
    return str(user_id) in licenses or user_id == ADMIN_USER_ID

def can_use(user_id, requested_sites_count):
    user_id_str = str(user_id)
    if is_authorized(user_id):
        return True, None
    current_count = usage_counts.get(user_id_str, 0)
    if current_count + requested_sites_count > FREE_LIMIT:
        return False, FREE_LIMIT - current_count
    return True, None

def update_usage(user_id, added_count):
    user_id_str = str(user_id)
    if not is_authorized(user_id):
        usage_counts[user_id_str] = usage_counts.get(user_id_str, 0) + added_count

# ذخیره وضعیت کاربران برای دریافت سایت‌ها یا فایل
user_states = {}

# حالت‌ها
STATE_AWAITING_URLS = 1
STATE_AWAITING_FILE = 2
STATE_AWAITING_LICENSE_USERID = 3

def send_usage_status(chat_id, user_id):
    if is_authorized(user_id):
        bot.send_message(chat_id, "شما لایسنس دارید و محدودیتی در استفاده ندارید.")
    else:
        used = usage_counts.get(str(user_id), 0)
        bot.send_message(chat_id, f"شما بدون لایسنس مجاز به اسکن {FREE_LIMIT} سایت هستید.\n"
                                  f"تاکنون {used} سایت اسکن کرده‌اید.")

@bot.message_handler(commands=['start'])
def cmd_start(message):
    bot.send_message(message.chat.id, "سلام! من ربات اسکنر XSS هستم.\n"
                                      "برای اسکن سایت‌ها لینک‌ها را با فاصله بفرستید یا فایل target.txt را آپلود کنید.\n"
                                      "اگر لایسنس دارید /license رو بزنید.\n"
                                      "ادمین هم می‌تواند با /addlicense لایسنس صادر کند.")
    send_usage_status(message.chat.id, message.from_user.id)

@bot.message_handler(commands=['license'])
def cmd_license(message):
    user_id = message.from_user.id
    if is_authorized(user_id):
        bot.send_message(message.chat.id, "شما لایسنس دارید و می‌توانید به صورت نامحدود از ربات استفاده کنید.")
    else:
        bot.send_message(message.chat.id, "شما لایسنس ندارید. برای استفاده بیشتر نیاز به لایسنس دارید.")

@bot.message_handler(commands=['addlicense'])
def cmd_addlicense(message):
    if message.from_user.id != ADMIN_USER_ID:
        bot.send_message(message.chat.id, "شما دسترسی ادمین ندارید.")
        return
    bot.send_message(message.chat.id, "آیدی تلگرام کاربری که می‌خواهید لایسنس بدهید را بفرستید:")
    user_states[message.chat.id] = STATE_AWAITING_LICENSE_USERID

@bot.message_handler(func=lambda m: user_states.get(m.chat.id) == STATE_AWAITING_LICENSE_USERID)
def handle_license_userid(message):
    try:
        new_user_id = int(message.text.strip())
        licenses.add(str(new_user_id))
        bot.send_message(message.chat.id, f"لایسنس به کاربر {new_user_id} داده شد.")
    except:
        bot.send_message(message.chat.id, "آیدی نامعتبر است. لطفاً یک عدد صحیح بفرستید.")
    user_states.pop(message.chat.id, None)

@bot.message_handler(content_types=['text'])
def handle_text(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    text = message.text.strip()
    if not text:
        return

    # اگر قبلاً درخواست آپلود فایل داده شده بود
    if user_states.get(chat_id) == STATE_AWAITING_FILE:
        bot.send_message(chat_id, "لطفاً فایل target.txt را آپلود کنید یا لینک سایت‌ها را ارسال کنید.")
        return

    # تشخیص اینکه متن لینک هست یا دستور
    if text.lower() == "clear":
        usage_counts[str(user_id)] = 0
        bot.send_message(chat_id, "تعداد استفاده شما ریست شد.")
        return


# اگر متن شامل چند لینک است، به صورت لیست جدا شده توسط خط یا فاصله
    urls = [line.strip() for line in text.split() if line.strip()]
    if len(urls) == 0:
        bot.send_message(chat_id, "لطفاً لینک یا فایل target.txt ارسال کنید.")
        return

    # در اینجا درخواست اسکن می‌دهیم
    bot.send_message(chat_id, f"درخواست شما دریافت شد. {len(urls)} سایت در صف اسکن قرار گرفت.")
    threading.Thread(target=scan_and_send_result, args=(chat_id, urls, None)).start()

@bot.message_handler(content_types=['document'])
def handle_document(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    file_info = message.document
    if file_info.file_name != "target.txt":
        bot.send_message(chat_id, "فایل باید با نام target.txt باشد.")
        return

    file = bot.download_file(bot.get_file(file_info.file_id).file_path)
    text_content = file.decode("utf-8")
    urls = [line.strip() for line in text_content.splitlines() if line.strip()]
    if len(urls) == 0:
        bot.send_message(chat_id, "فایل خالی است یا لینکی در آن نیست.")
        return

    bot.send_message(chat_id, f"{len(urls)} سایت در فایل دریافت شد و در صف اسکن قرار گرفت.")
    threading.Thread(target=scan_and_send_result, args=(chat_id, urls, None)).start()

def scan_and_send_result(chat_id, urls, params):
    user_id = chat_id  # چون چت تک نفره هست
    allowed, remaining = can_use(user_id, len(urls))
    if not allowed:
        bot.send_message(chat_id, f"شما بدون لایسنس فقط مجاز به اسکن {FREE_LIMIT} سایت هستید.\n"
                                  f"شما قبلاً {FREE_LIMIT - remaining} سایت اسکن کردید.\n"
                                  f"لطفاً برای ادامه از ادمین لایسنس بگیرید.")
        return

    update_usage(user_id, len(urls))

    scanner = XSSScan()
    all_results = []

    for url in urls:
        url = url.strip()
        if not url:
            continue
        bot.send_message(chat_id, f"در حال اسکن: {url}")
        result = scanner.run(url, params_to_test=params)
        all_results.append((url, result))

    message = ""
    for url, res in all_results:
        message += f"نتایج اسکن برای: {url}\n"
        if isinstance(res, str) and res == "ایمن":
            message += "هیچ آسیب‌پذیری XSS پیدا نشد.\n\n"
        else:
            for vuln in res:
                message += f"- نوع: {vuln.get('type')}\n"
                message += f"  پارامتر: {vuln.get('param', 'N/A')}\n"
                message += f"  پیلود: {vuln.get('payload')}\n"
                message += f"  آدرس: {vuln.get('url')}\n\n"
    if not message:
        message = "هیچ نتیجه‌ای برای اسکن پیدا نشد."

    bot.send_message(chat_id, message)

if name == 'main':
    print("ربات شروع به کار کرد...")
    bot.infinity_polling()