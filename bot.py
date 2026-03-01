# =========================
# IMPORTS
# =========================
import os
import re
import json
import logging
import time
from datetime import datetime

from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# =========================
# LOAD ENV
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
SERVICE_JSON = json.loads(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"))

# =========================
# LOGGING
# =========================
logging.basicConfig(level=logging.INFO)

# =========================
# GOOGLE SHEET CONNECT
# =========================
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
creds = ServiceAccountCredentials.from_json_keyfile_dict(SERVICE_JSON, scope)
gc = gspread.authorize(creds)

users_sheet = gc.open_by_key(GOOGLE_SHEET_ID).worksheet("USERS")
settings_sheet = gc.open_by_key(GOOGLE_SHEET_ID).worksheet("SETTINGS")

# =========================
# SETTINGS HELPERS
# =========================
def get_setting(key):
    records = settings_sheet.get_all_records()
    for r in records:
        if r["KEY"] == key:
            return r["VALUE"]
    return None

def update_setting(key, value):
    cell = settings_sheet.find(key)
    settings_sheet.update_cell(cell.row, 2, value)

# =========================
# USER HELPERS
# =========================
def get_user(tg_id):
    users = users_sheet.get_all_records()
    for i, u in enumerate(users, start=2):
        if str(u["TG_ID"]) == str(tg_id):
            return i, u
    return None, None

def count_referrals(tg_id):
    users = users_sheet.get_all_records()
    return sum(1 for u in users if str(u["REFERRED_BY"]) == str(tg_id))

def can_withdraw(user_data):
    min_balance = int(get_setting("MIN_WITHDRAW"))
    min_ref = int(get_setting("MIN_REFERRAL"))

    if int(user_data["MAIN_BALANCE"]) < min_balance:
        return False, "❌ Minimum withdraw balance পূরণ হয়নি"

    if count_referrals(user_data["TG_ID"]) < min_ref:
        return False, "❌ Minimum referral পূরণ হয়নি"

    return True, "✅ Eligible"

def unlock_referral_bonus(row, user_data):
    bonus = int(user_data["REFERRAL_BONUS"])
    main = int(user_data["MAIN_BALANCE"])

    if bonus > 0:
        users_sheet.update_cell(row, 7, main + bonus)
        users_sheet.update_cell(row, 8, 0)

def add_referral_bonus(user_row, user_data, referrer_tg):
    user_bonus = int(get_setting("REF_BONUS_USER"))
    ref_bonus = int(get_setting("REF_BONUS_REFERRER"))

    users_sheet.update_cell(
        user_row,
        8,
        int(user_data["REFERRAL_BONUS"]) + user_bonus
    )

    ref_row, ref_data = get_user(referrer_tg)
    if ref_row:
        users_sheet.update_cell(
            ref_row,
            8,
            int(ref_data["REFERRAL_BONUS"]) + ref_bonus
        )

def create_user(tg_id, name, gmail, ref):
    last_id = int(get_setting("LAST_USER_ID"))
    new_id = last_id + 1

    users_sheet.append_row([
        new_id,                             # USER_ID
        tg_id,                              # TG_ID
        name,                               # NAME
        gmail,                              # GMAIL
        datetime.now().strftime("%Y-%m-%d"),
        ref,                                # REFERRED_BY
        0,                                  # MAIN_BALANCE
        0,                                  # REFERRAL_BONUS (LOCKED)
        0,                                  # COMMISSION
        "ACTIVE"                            # STATUS
    ])

    update_setting("LAST_USER_ID", new_id)

    if ref:
        time.sleep(1)
        row, data = get_user(tg_id)
        add_referral_bonus(row, data, ref)

    return new_id

# =========================
# TEXT BLOCKS
# =========================
START_TEXT = """
👋 Welcome to SN Online Earning Bot

💼 একটি নির্ভরযোগ্য অনলাইন আর্নিং প্ল্যাটফর্ম
🎯 সহজ ও স্বচ্ছ কাজের মাধ্যমে SN রিওয়ার্ড 
🎁 বোনাস ও রিওয়ার্ড সিস্টেম সুবিধা
💸 দ্রুত Withdraw সাপোর্ট

⭐ নতুন ইউজারদের জন্য বিশেষ সুবিধা ও ১০০ SN রিওয়ার্ড
⭐ নিয়মিত টাস্ক ও আপডেট যুক্ত হয়

👇 শুরু করতে নিচের Continue বাটনে ট্যাপ করুন
"""

TERMS_TEXT = """
📜 Terms & Conditions

• Telegram / Google / Facebook এর নিয়ম ভাঙা যাবে না
• একাধিক একাউন্ট নিষিদ্ধ
• ফেক কাজ বা abuse করলে একাউন্ট বাতিল
• আইনবিরোধী কাজে সম্পূর্ণ দায় ইউজারের
• এটি একটি অনলাইন আর্নিং প্ল্যাটফর্ম
• সব সময় দততার সাথে কাজ করতে হবে
• আপনার কাজ এর উপর ভিত্তি করে আপনার আয় হবে
• কোনো নির্দিষ্ট আয় নিশ্চিত করা হয় না
• সব কাজ নিজ দায়িত্বে করতে হবে
• আপনি স্বীকার করছেন, এই কাজ এর জন্য আপনাকে কেও জোর করছে না, আপনি নিজের ইচ্ছায় এই কাজ  করছেন।
• Privacy লঙ্ঘন হয় এমন কাজ করা যাবে না
• এই প্ল্যাটফর্ম এর বিরূদ্ধ ষড়যন্ত্র, ভুয়া তথ্য প্রচার করলে আইনগত অপরাধ বলে গন্য হবে
• নিয়ম ভঙ্গ করলে, কতৃপক্ষ আইনপগত ব্যবস্থা সহ যে কোনো সিদ্ধান্ত গ্রহন করতে পারে
✅ Accept না করলে ব্যবহার করা যাবে না
"""

# =========================
# BOT FLOW
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if args:
        context.user_data["ref"] = args[0]

    kb = [[InlineKeyboardButton("➡️ Continue", callback_data="continue")]]
    await update.message.reply_text(
        START_TEXT,
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def show_terms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    kb = [
        [
            InlineKeyboardButton("✅ Accept", callback_data="accept"),
            InlineKeyboardButton("❌ Decline", callback_data="decline"),
        ]
    ]
    await q.message.reply_text(
        TERMS_TEXT,
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def accept_terms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["step"] = "gmail"
    await q.message.reply_text("📧 আপনার Gmail দিন")

async def decline_terms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("❌ Accept না করলে বট ব্যবহার করা যাবে না")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("step")

    if step == "gmail":
        gmail = update.message.text.strip()
        if not re.match(r"^[A-Za-z0-9._%+-]+@gmail\.com$", gmail):
            await update.message.reply_text("❌ সঠিক Gmail দিন")
            return
        context.user_data["gmail"] = gmail
        context.user_data["step"] = "name"
        await update.message.reply_text("👤 আপনার নাম লিখুন")
        return

    if step == "name":
        tg_id = update.message.from_user.id
        name = update.message.text.strip()
        ref = context.user_data.get("ref", "")

        create_user(tg_id, name, context.user_data["gmail"], ref)
        context.user_data.clear()

        await update.message.reply_text(
            "✅ Registration Successful!\n🎉 Welcome to SN Online Earning"
        )

# =========================
# MAIN
# =========================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(show_terms, pattern="continue"))
    app.add_handler(CallbackQueryHandler(accept_terms, pattern="accept"))
    app.add_handler(CallbackQueryHandler(decline_terms, pattern="decline"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()

if __name__ == "__main__":
    main()
