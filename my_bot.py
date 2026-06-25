import sqlite3
import requests
import logging
import asyncio
import re

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# --- الإعدادات ---
BOT_TOKEN = "8960056224:AAGMIz19XsxzA7u81NGu8X6tgSL3awwlMSE"
API_KEY = "758ce41e3232ffe511f240c4d184fdb4"
ADMIN_ID = 8201315070
SMMWIZ_URL = "https://smmwiz.com/api/v2"
WHATSAPP_LINK = "https://wa.me/201011496150"

logging.basicConfig(level=logging.INFO)

# --- هيكلة الخدمات ---
CATEGORIES = {
    "insta": {
        "name": "📸 Instagram",
        "services": {
            "17678": {"name": "Followers", "price": 35},
            "20216": {"name": "Likes", "price": 20},
            "14245": {"name": "Views", "price": 6}
        }
    },
    "fb": {
        "name": "🔵 Facebook",
        "services": {
            "17333": {"name": "Followers", "price": 35},
            "2981": {"name": "Likes", "price": 20}
        }
    },
    "tiktok": {
        "name": "🎵 TikTok",
        "services": {
            "11775": {"name": "Likes", "price": 20},
            "19967": {"name": "Views", "price": 6}
        }
    }
}

# --- تهيئة البوت وقاعدة البيانات ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db = sqlite3.connect("store.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, balance REAL DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, user_id INTEGER, status TEXT)")
db.commit()

class UserStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_amount = State()
    waiting_for_photo = State()
    waiting_for_quantity = State()
    waiting_for_link = State()

# --- دالة مراقبة الطلبات ---
async def check_order_status():
    while True:
        cursor.execute("SELECT order_id, user_id FROM orders WHERE status != 'Completed'")
        orders = cursor.fetchall()
        for o_id, u_id in orders:
            try:
                req = requests.post(SMMWIZ_URL, data={'key': API_KEY, 'action': 'status', 'order': o_id})
                if req.status_code == 200:
                    status = req.json().get('status')
                    if status == 'Pending':
                        await bot.send_message(u_id, "⏳ *طلبك قيد الانتظار*، يرجى الانتظار دقيقتين حتى يبدأ التنفيذ.")
                    elif status == 'In Progress':
                        cursor.execute("UPDATE orders SET status = 'Completed' WHERE order_id = ?", (o_id,))
                        db.commit()
                        await bot.send_message(u_id, "🚀 *جاري تنفيذ طلبك الآن!* سيكتمل خلال 5 دقائق.")
            except: pass
        await asyncio.sleep(120)

# --- القائمة الرئيسية ---
def main_menu():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🛒 شراء خدمات", callback_data="categories")],
        [types.InlineKeyboardButton(text="💰 شحن الرصيد", callback_data="add_balance")],
        [types.InlineKeyboardButton(text="💳 لوحة التحكم", callback_data="check_balance")],
        [types.InlineKeyboardButton(text="🎧 تواصل مع الدعم الفني", url=WHATSAPP_LINK)]
    ])

# --- الدوال البرمجية ---
@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT name FROM users WHERE user_id=?", (message.from_user.id,))
    if not cursor.fetchone():
        await message.answer("أهلاً بك في Tik Wolf! 🐺\nيرجى كتابة اسمك للبدء:")
        await state.set_state(UserStates.waiting_for_name)
    else:
        await message.answer("مرحباً بك مجدداً! اختر الخدمة المطلوبة:", reply_markup=main_menu())

@dp.message(UserStates.waiting_for_name)
async def set_name(message: types.Message, state: FSMContext):
    cursor.execute("INSERT INTO users (user_id, name, balance) VALUES (?, ?, 0)", (message.from_user.id, message.text))
    db.commit()
    await message.answer("تم حفظ بياناتك بنجاح! ✅", reply_markup=main_menu())
    await state.clear()

@dp.callback_query(F.data == "check_balance")
async def show_dashboard(call: types.CallbackQuery):
    cursor.execute("SELECT name, balance FROM users WHERE user_id=?", (call.from_user.id,))
    user = cursor.fetchone()
    name, bal = user if user else ("غير مسجل", 0)
    dashboard = (
        f"📊 ── **لوحة تحكم المستخدم** ── 📊\n\n"
        f"👤 الاسم: {name}\n\n"
        f"💰 الرصيد الحالي: {bal} ج.م\n\n"
        f"🆔 ID: {call.from_user.id}\n\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    await call.message.edit_text(dashboard, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="main_menu")]]))

@dp.callback_query(F.data == "add_balance")
async def add_balance(call: types.CallbackQuery, state: FSMContext):
    txt = (
        "💰 ── **نظام شحن الرصيد** ── 💰\n\n"
        "يرجى تحويل المبلغ المطلوب إلى الرقم التالي:\n"
        "📞 `01011496150`\n\n"
        "متاح التحويل عبر:\n"
        "✅ Vodafone Cash\n"
        "✅ InstaPay\n\n"
        "━━━━━━ ⚠️ تنبيه ━━━━━━\n"
        "بعد إتمام التحويل، أرسل المبلغ (أرقام فقط) في الرسالة التالية:"
    )
    await call.message.edit_text(txt, parse_mode="Markdown", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="🔙 رجوع", callback_data="main_menu")]]))
    await state.set_state(UserStates.waiting_for_amount)

@dp.message(UserStates.waiting_for_amount)
async def get_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("❌ يرجى إدخال أرقام فقط!")
    await state.update_data(amount=message.text)
    await message.answer("✅ تمام، أرسل سكرين شوت التحويل للمراجعة:")
    await state.set_state(UserStates.waiting_for_photo)

@dp.message(UserStates.waiting_for_photo, F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    amt = data.get('amount')
    kb = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="✅ قبول", callback_data=f"app_{message.from_user.id}_{amt}"), types.InlineKeyboardButton(text="❌ رفض", callback_data=f"rej_")]])
    await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"💸 إيداع: {amt} ج من {message.from_user.full_name}", reply_markup=kb)
    await message.answer("تم إرسال الطلب للإدارة. سيتم الشحن فور المراجعة.")
    await state.clear()

@dp.callback_query(F.data == "categories")
async def show_categories(call: types.CallbackQuery):
    btns = [[types.InlineKeyboardButton(text=v['name'], callback_data=f"cat_{k}")] for k, v in CATEGORIES.items()]
    btns.append([types.InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="main_menu")])
    await call.message.edit_text("✨ **قائمة المنصات المتاحة** ✨", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("cat_"))
async def show_services(call: types.CallbackQuery):
    cat_id = call.data.split("_")[1]
    msg = f"🔥 **خدمات {CATEGORIES[cat_id]['name']}** 🔥\n\nاختر الخدمة لبدء الطلب:\n"
    btns = [[types.InlineKeyboardButton(text=f"✨ {v['name']} | السعر: {v['price']} ج", callback_data=f"buy_{cat_id}_{sid}")] for sid, v in CATEGORIES[cat_id]['services'].items()]
    btns.append([types.InlineKeyboardButton(text="🔙 رجوع", callback_data="categories")])
    await call.message.edit_text(msg, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("buy_"))
async def select_service(call: types.CallbackQuery, state: FSMContext):
    _, cat, sid = call.data.split("_")
    await state.update_data(sid=sid, cat=cat)
    await call.message.answer("📝 أدخل الكمية المطلوبة:")
    await state.set_state(UserStates.waiting_for_quantity)

@dp.message(UserStates.waiting_for_quantity)
async def get_qty(msg: types.Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("❌ يجب إدخال أرقام فقط!")
    qty = int(msg.text)
    data = await state.get_data()
    total = (qty / 1000) * CATEGORIES[data['cat']]['services'][data['sid']]['price']
    await state.update_data(qty=qty, total=total)
    await msg.answer(f"💰 التكلفة الإجمالية: {total} ج.م\n🔗 أرسل الرابط الآن للتنفيذ:")
    await state.set_state(UserStates.waiting_for_link)

@dp.message(UserStates.waiting_for_link)
async def finish_order(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    req = requests.post(SMMWIZ_URL, data={'key': API_KEY, 'action': 'add', 'service': data['sid'], 'link': msg.text, 'quantity': data['qty']})
    if req.status_code == 200:
        cursor.execute("INSERT INTO orders VALUES (?, ?, 'Pending')", (req.json()['order'], msg.from_user.id))
        db.commit()
        await msg.answer("✅ تم إرسال طلبك بنجاح! سنقوم بإخطارك عند بدء التنفيذ.")
    else: await msg.answer("❌ خطأ في الاتصال بالسيرفر.")
    await state.clear()

@dp.callback_query(F.data.startswith("app_"))
async def approve(call: types.CallbackQuery):
    _, uid, amt = call.data.split("_")
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amt, uid))
    db.commit()
    await call.message.edit_caption(caption="✅ تمت الموافقة.")
    await bot.send_message(uid, f"🎉 تم شحن رصيدك بـ {amt} ج!")

@dp.callback_query(F.data == "main_menu")
async def back_to_main(call: types.CallbackQuery):
    await call.message.edit_text("🏠 القائمة الرئيسية:", reply_markup=main_menu())

async def main():
    asyncio.create_task(check_order_status())
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
