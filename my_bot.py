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
BOT_TOKEN = "8960056224:AAEeYf2SxBa9rfyUEzEnLEf2HGIK5K1Pfrw"
API_KEY = "3ea10a856b380134944184dfd394454c"
ADMIN_ID = 8201315070
SMMWIZ_URL = "https://smmwiz.com/api/v2"
WHATSAPP_LINK = "https://wa.me/201011496150"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

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
            "19968": {"name": "Views", "price": 6}
        }
    }
}

# --- قاعدة البيانات ---
db = sqlite3.connect("store.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, balance REAL DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, user_id INTEGER, status TEXT)")
db.commit()

# --- الحالات ---
class UserStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_amount = State()
    waiting_for_photo = State()
    waiting_for_quantity = State()
    waiting_for_link = State()

# --- القائمة الرئيسية ---
def main_kb():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🛒 شراء خدمات", callback_data="categories")],
        [types.InlineKeyboardButton(text="💰 شحن الرصيد", callback_data="add_balance")],
        [types.InlineKeyboardButton(text="💳 لوحة التحكم", callback_data="check_balance")],
        [types.InlineKeyboardButton(text="🎧 تواصل مع الدعم", url=WHATSAPP_LINK)]
    ])

# --- مراقبة الطلبات تلقائياً ---
async def check_order_status():
    while True:
        cursor.execute("SELECT order_id, user_id FROM orders WHERE status != 'Completed'")
        for o_id, u_id in cursor.fetchall():
            try:
                req = requests.post(SMMWIZ_URL, data={'key': API_KEY, 'action': 'status', 'order': o_id})
                if req.status_code == 200 and req.json().get('status') == 'Completed':
                    cursor.execute("UPDATE orders SET status = 'Completed' WHERE order_id = ?", (o_id,))
                    db.commit()
                    await bot.send_message(u_id, "🚀 تم تنفيذ طلبك بنجاح!")
            except: pass
        await asyncio.sleep(120)

# --- الدوال البرمجية ---

@dp.message(Command("start"))
async def start(msg: types.Message, state: FSMContext):
    cursor.execute("SELECT name FROM users WHERE user_id=?", (msg.from_user.id,))
    if not cursor.fetchone():
        await msg.answer("أهلاً بك! اكتب اسمك للبدء:")
        await state.set_state(UserStates.waiting_for_name)
    else:
        await msg.answer("مرحباً بك! اختر الخدمة:", reply_markup=main_kb())

@dp.message(UserStates.waiting_for_name)
async def set_name(msg: types.Message, state: FSMContext):
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, 0)", (msg.from_user.id, msg.text))
    db.commit()
    await msg.answer("تم الحفظ!", reply_markup=main_kb())
    await state.clear()

@dp.callback_query(F.data == "main_menu")
async def back_to_main(call: types.CallbackQuery):
    await call.message.edit_text("🏠 القائمة الرئيسية:", reply_markup=main_kb())

@dp.callback_query(F.data == "check_balance")
async def show_dash(call: types.CallbackQuery):
    cursor.execute("SELECT name, balance FROM users WHERE user_id=?", (call.from_user.id,))
    name, bal = cursor.fetchone()
    await call.message.edit_text(f"📊 الرصيد: {bal} ج.م", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="🔙 رجوع", callback_data="main_menu")]]))

@dp.callback_query(F.data == "add_balance")
async def add_bal(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text("💰 للتحويل: 01011496150\nأرسل المبلغ:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="🔙 رجوع", callback_data="main_menu")]]))
    await state.set_state(UserStates.waiting_for_amount)

@dp.message(UserStates.waiting_for_amount)
async def get_amount(msg: types.Message, state: FSMContext):
    await state.update_data(amount=msg.text)
    await msg.answer("✅ أرسل صورة الإيصال:")
    await state.set_state(UserStates.waiting_for_photo)

@dp.message(UserStates.waiting_for_photo, F.photo)
async def handle_photo(msg: types.Message, state: FSMContext):
    await bot.send_photo(ADMIN_ID, msg.photo[-1].file_id, caption="💸 إيداع جديد!")
    await msg.answer("تم إرسال الطلب للمراجعة.")
    await state.clear()

@dp.callback_query(F.data == "categories")
async def show_cats(call: types.CallbackQuery):
    btns = [[types.InlineKeyboardButton(text=v['name'], callback_data=f"cat_{k}")] for k, v in CATEGORIES.items()]
    btns.append([types.InlineKeyboardButton(text="🔙 رجوع", callback_data="main_menu")])
    await call.message.edit_text("🛒 اختر المنصة:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("cat_"))
async def show_servs(call: types.CallbackQuery):
    cat = call.data.split("_")[1]
    btns = [[types.InlineKeyboardButton(text=f"✨ {v['name']} | {v['price']} ج / 1000", callback_data=f"buy_{cat}_{sid}")] for sid, v in CATEGORIES[cat]['services'].items()]
    btns.append([types.InlineKeyboardButton(text="🔙 رجوع", callback_data="categories")])
    await call.message.edit_text(f"🔥 خدمات {CATEGORIES[cat]['name']}:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("buy_"))
async def buy_s(call: types.CallbackQuery, state: FSMContext):
    _, cat, sid = call.data.split("_")
    await state.update_data(sid=sid, cat=cat)
    await call.message.answer("📝 أدخل الكمية:")
    await state.set_state(UserStates.waiting_for_quantity)

@dp.message(UserStates.waiting_for_quantity)
async def get_qty(msg: types.Message, state: FSMContext):
    await state.update_data(qty=msg.text)
    await msg.answer("🔗 أرسل الرابط:")
    await state.set_state(UserStates.waiting_for_link)

@dp.message(UserStates.waiting_for_link)
async def finish(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    req = requests.post(SMMWIZ_URL, data={'key': API_KEY, 'action': 'add', 'service': data['sid'], 'link': msg.text, 'quantity': data['qty']})
    if req.status_code == 200:
        cursor.execute("INSERT INTO orders VALUES (?, ?, 'Pending')", (req.json()['order'], msg.from_user.id))
        db.commit()
        await msg.answer("✅ تم إرسال الطلب!")
    await state.clear()

async def main():
    asyncio.create_task(check_order_status())
    await dp.start_polling(bot)

if __name__ == "__main__": asyncio.run(main())
