import sqlite3
import requests
import logging
import asyncio
import sys
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# --- [إعدادات النظام والاتصال] ---
BOT_TOKEN = "8960056224:AAGMIz19XsxzA7u81NGu8X6tgSL3awwlMSE"
API_KEY = "758ce41e3232ffe511f240c4d184fdb4"
ADMIN_ID = 8201315070
SMMWIZ_URL = "https://smmwiz.com/api/v2"
WHATSAPP_LINK = "https://wa.me/201011496150"

# --- [إعداد نظام التوثيق Logging] ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("TikWolfBot")

# --- [تهيئة البوت وقاعدة البيانات] ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db = sqlite3.connect("store.db", check_same_thread=False)
cursor = db.cursor()

def init_db():
    cursor.execute("""CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, name TEXT, balance REAL DEFAULT 0)""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS orders 
                      (order_id TEXT PRIMARY KEY, user_id INTEGER, status TEXT, cost REAL)""")
    db.commit()
    logger.info("تم التحقق من قاعدة البيانات.")

init_db()

# --- [تعريف الخدمات] ---
CATEGORIES = {
    "insta": {"name": "📸 Instagram", "services": {"17678": {"name": "Followers", "price": 35}}},
    "fb": {"name": "🔵 Facebook", "services": {"17333": {"name": "Followers", "price": 35}}},
    "tiktok": {"name": "🎵 TikTok", "services": {"11775": {"name": "Likes", "price": 20}}}
}

class UserStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_amount = State()
    waiting_for_photo = State()
    waiting_for_qty = State()
    waiting_for_link = State()

# --- [دوال الواجهات] ---
def get_main_kb():
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🛒 شراء خدمات", callback_data="cats")],
        [types.InlineKeyboardButton(text="💰 شحن الرصيد", callback_data="add_bal")],
        [types.InlineKeyboardButton(text="💳 لوحة التحكم", callback_data="profile")],
        [types.InlineKeyboardButton(text="🎧 دعم فني", url=WHATSAPP_LINK)]
    ])
    return kb

# --- [دالة مراقبة الطلبات الخلفية] ---
async def monitor_orders():
    while True:
        try:
            cursor.execute("SELECT order_id, user_id FROM orders WHERE status != 'Completed'")
            for o_id, u_id in cursor.fetchall():
                req = requests.post(SMMWIZ_URL, data={'key': API_KEY, 'action': 'status', 'order': o_id}).json()
                if req.get('status') == 'Completed':
                    cursor.execute("UPDATE orders SET status = 'Completed' WHERE order_id = ?", (o_id,))
                    db.commit()
                    await bot.send_message(u_id, "✅ تم تنفيذ طلبك بنجاح!")
        except Exception as e:
            logger.error(f"Error monitoring: {e}")
        await asyncio.sleep(300)

# --- [معالجة الأوامر] ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    cursor.execute("SELECT name FROM users WHERE user_id=?", (message.from_user.id,))
    if not cursor.fetchone():
        await message.answer("أهلاً بك! يرجى كتابة اسمك:")
        await state.set_state(UserStates.waiting_for_name)
    else:
        await message.answer("القائمة الرئيسية:", reply_markup=get_main_kb())

@dp.message(UserStates.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    cursor.execute("INSERT INTO users (user_id, name) VALUES (?, ?)", (message.from_user.id, message.text))
    db.commit()
    await message.answer("تم حفظ بياناتك!", reply_markup=get_main_kb())
    await state.clear()

@dp.callback_query(F.data == "profile")
async def show_profile(call: types.CallbackQuery):
    cursor.execute("SELECT name, balance FROM users WHERE user_id=?", (call.from_user.id,))
    user = cursor.fetchone()
    text = f"📊 **ملفك الشخصي**\n\n👤 الاسم: {user[0]}\n\n💰 الرصيد: {user[1]} ج.م"
    await call.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="🔙 عودة", callback_data="main")]]), parse_mode="Markdown")

@dp.callback_query(F.data == "add_bal")
async def add_bal(call: types.CallbackQuery, state: FSMContext):
    await call.message.edit_text("💰 **شحن الرصيد**\nفودافون كاش: `01011496150`\nأرسل المبلغ:", parse_mode="Markdown")
    await state.set_state(UserStates.waiting_for_amount)

@dp.message(UserStates.waiting_for_amount)
async def process_amount(message: types.Message, state: FSMContext):
    await state.update_data(amount=message.text)
    await message.answer("أرسل سكرين التحويل:")
    await state.set_state(UserStates.waiting_for_photo)

@dp.message(UserStates.waiting_for_photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    amt = data['amount']
    kb = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="✅ قبول", callback_data=f"app_{message.from_user.id}_{amt}")]])
    await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"إيداع: {amt} من {message.from_user.full_name}", reply_markup=kb)
    await message.answer("تم الإرسال للمراجعة.")
    await state.clear()

@dp.callback_query(F.data.startswith("app_"))
async def approve_bal(call: types.CallbackQuery):
    _, uid, amt = call.data.split("_")
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amt, uid))
    db.commit()
    await call.message.edit_caption(caption="✅ تمت الموافقة.")
    await bot.send_message(uid, "تم إضافة الرصيد!")

@dp.callback_query(F.data == "cats")
async def show_cats(call: types.CallbackQuery):
    btns = [[types.InlineKeyboardButton(text=v['name'], callback_data=f"cat_{k}")] for k, v in CATEGORIES.items()]
    btns.append([types.InlineKeyboardButton(text="🔙 عودة", callback_data="main")])
    await call.message.edit_text("اختر المنصة:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data == "main")
async def main_menu(call: types.CallbackQuery):
    await call.message.edit_text("القائمة الرئيسية:", reply_markup=get_main_kb())

async def main():
    logger.info("بدء تشغيل النظام...")
    asyncio.create_task(monitor_orders())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
