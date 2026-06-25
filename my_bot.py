import sqlite3
import requests
import logging
import asyncio
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
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db = sqlite3.connect("store.db", check_same_thread=False)
cursor = db.cursor()

# إنشاء الجداول
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, balance REAL DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, user_id INTEGER, status TEXT)")
db.commit()

CATEGORIES = {
    "insta": {"name": "📸 Instagram", "services": {"17678": {"name": "Followers", "price": 35}, "20216": {"name": "Likes", "price": 20}}},
    "fb": {"name": "🔵 Facebook", "services": {"17333": {"name": "Followers", "price": 35}, "2981": {"name": "Likes", "price": 20}}},
    "tiktok": {"name": "🎵 TikTok", "services": {"11775": {"name": "Likes", "price": 20}, "19967": {"name": "Views", "price": 6}}}
}

class UserStates(StatesGroup):
    name = State(); amount = State(); photo = State(); qty = State(); link = State()

# --- القوائم ---
def main_kb():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🛒 شراء خدمات", callback_data="cats")],
        [types.InlineKeyboardButton(text="💰 شحن (InstaPay / VF Cash)", callback_data="add_bal")],
        [types.InlineKeyboardButton(text="💳 لوحة التحكم", callback_data="profile")],
        [types.InlineKeyboardButton(text="🎧 الدعم الفني", url=WHATSAPP_LINK)]
    ])

# --- المراقبة ---
async def monitor():
    while True:
        cursor.execute("SELECT order_id, user_id FROM orders WHERE status != 'Completed'")
        for o_id, u_id in cursor.fetchall():
            try:
                res = requests.post(SMMWIZ_URL, data={'key': API_KEY, 'action': 'status', 'order': o_id}).json()
                if res.get('status') == 'Completed':
                    cursor.execute("UPDATE orders SET status = 'Completed' WHERE order_id = ?", (o_id,))
                    db.commit(); await bot.send_message(u_id, "✅ تم تنفيذ طلبك!")
            except: pass
        await asyncio.sleep(120)

# --- الهاندلرز ---
@dp.message(Command("start"))
async def start(msg: types.Message, state: FSMContext):
    cursor.execute("SELECT name FROM users WHERE user_id=?", (msg.from_user.id,))
    if not cursor.fetchone():
        await msg.answer("أهلاً بك! اكتب اسمك:"); await state.set_state(UserStates.name)
    else: await msg.answer("مرحباً بك في القائمة الرئيسية:", reply_markup=main_kb())

@dp.message(UserStates.name)
async def set_name(msg: types.Message, state: FSMContext):
    cursor.execute("INSERT INTO users (user_id, name) VALUES (?, ?)", (msg.from_user.id, msg.text)); db.commit()
    await msg.answer("تم! ✅", reply_markup=main_kb()); await state.clear()

@dp.callback_query(F.data == "profile")
async def profile(call: types.CallbackQuery):
    cursor.execute("SELECT name, balance FROM users WHERE user_id=?", (call.from_user.id,))
    n, b = cursor.fetchone()
    text = f"📊 **لوحة التحكم**\n\n👤 الاسم: {n}\n\n💰 الرصيد: {b} ج.م"
    await call.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="🔙 رجوع", callback_data="main")]]), parse_mode="Markdown")

@dp.callback_query(F.data == "add_bal")
async def add(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text("💰 شحن الرصيد:\nفودافون كاش: 01011496150\nأرسل المبلغ:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="🔙 رجوع", callback_data="main")]]))
    await state.set_state(UserStates.amount)

@dp.message(UserStates.amount)
async def get_amt(msg: types.Message, state: FSMContext):
    await state.update_data(amt=msg.text); await msg.answer("أرسل سكرين التحويل:"); await state.set_state(UserStates.photo)

@dp.message(UserStates.photo, F.photo)
async def get_photo(msg: types.Message, state: FSMContext):
    d = await state.get_data(); kb = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="✅ قبول", callback_data=f"app_{msg.from_user.id}_{d['amt']}")], [types.InlineKeyboardButton(text="❌ رجوع", callback_data="main")]])
    await bot.send_photo(ADMIN_ID, msg.photo[-1].file_id, caption=f"إيداع: {d['amt']} من {msg.from_user.full_name}", reply_markup=kb)
    await msg.answer("تم الإرسال للإدارة."); await state.clear()

@dp.callback_query(F.data.startswith("app_"))
async def app(call: types.CallbackQuery):
    _, uid, amt = call.data.split("_")
    cursor.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amt, uid)); db.commit()
    await call.message.edit_caption(caption="تم."); await bot.send_message(uid, "تم شحن رصيدك!")

@dp.callback_query(F.data == "cats")
async def cats(call: types.CallbackQuery):
    btns = [[types.InlineKeyboardButton(text=v['name'], callback_data=f"cat_{k}")] for k, v in CATEGORIES.items()]; btns.append([types.InlineKeyboardButton(text="🔙 رجوع", callback_data="main")])
    await call.message.edit_text("اختر المنصة:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("cat_"))
async def srv(call: types.CallbackQuery):
    cat = call.data.split("_")[1]; btns = [[types.InlineKeyboardButton(text=f"{v['name']} ({v['price']}ج)", callback_data=f"buy_{cat}_{sid}")] for sid, v in CATEGORIES[cat]['services'].items()]; btns.append([types.InlineKeyboardButton(text="🔙 رجوع", callback_data="cats")])
    await call.message.edit_text("اختر:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("buy_"))
async def buy(call: types.CallbackQuery, state: FSMContext):
    _, cat, sid = call.data.split("_"); await state.update_data(cat=cat, sid=sid); await call.message.answer("الكمية؟"); await state.set_state(UserStates.qty)

@dp.message(UserStates.qty)
async def get_qty(msg: types.Message, state: FSMContext):
    await state.update_data(qty=msg.text); await msg.answer("الرابط؟"); await state.set_state(UserStates.link)

@dp.message(UserStates.link)
async def fin(msg: types.Message, state: FSMContext):
    d = await state.get_data(); cursor.execute("SELECT balance FROM users WHERE user_id=?", (msg.from_user.id,)); bal = cursor.fetchone()[0]
    price = (int(d['qty'])/1000) * CATEGORIES[d['cat']]['services'][d['sid']]['price']
    if bal >= price:
        req = requests.post(SMMWIZ_URL, data={'key': API_KEY, 'action': 'add', 'service': d['sid'], 'link': msg.text, 'quantity': d['qty']}).json()
        if 'order' in req:
            cursor.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (price, msg.from_user.id)); cursor.execute("INSERT INTO orders VALUES (?, ?, 'Pending')", (req['order'], msg.from_user.id)); db.commit()
            await msg.answer("✅ تم الطلب!"); await state.clear()
    else: await msg.answer("❌ رصيد غير كافٍ.")

@dp.callback_query(F.data == "main")
async def back(call: types.CallbackQuery): await call.message.edit_text("🏠 القائمة الرئيسية:", reply_markup=main_kb())

async def main():
    asyncio.create_task(monitor()); await dp.start_polling(bot)

if __name__ == "__main__": asyncio.run(main())
