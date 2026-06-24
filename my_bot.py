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
API_KEY = "e20891c4d8d4db32fc1bc53f173c0f1e"
ADMIN_ID = 8201315070
SMMWIZ_URL = "https://smmwiz.com/api/v2"

# --- قائمة الخدمات (تمت إضافتها) ---
SERVICES = {
    "17678": {"name": "متابعين انستقرام", "price": 35},
    "17333": {"name": "متابعين فيسبوك", "price": 35},
    "20216": {"name": "لايكات انستقرام", "price": 20},
    "11775": {"name": "لايكات تيك توك", "price": 20},
    "19968": {"name": "مشاهدات تيك توك", "price": 6},
}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db = sqlite3.connect("store.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, balance REAL DEFAULT 0)")
db.commit()

# --- الحالات ---
class Reg(StatesGroup): name = State()
class Pay(StatesGroup): amt = State(); photo = State()
class Order(StatesGroup): sid = State(); qty = State(); link = State()

# --- القائمة الرئيسية ---
def main_menu():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🛒 شراء خدمات", callback_data="show_services")],
        [types.InlineKeyboardButton(text="💰 شحن الرصيد", callback_data="add_balance")]
    ])

@dp.message(Command("start"))
async def start(msg: types.Message, state: FSMContext):
    cursor.execute("SELECT name FROM users WHERE user_id=?", (msg.from_user.id,))
    if not cursor.fetchone():
        await msg.answer("أهلاً بك في TikWolf! 🐺 اكتب اسمك:")
        await state.set_state(Reg.name)
    else:
        await msg.answer("مرحباً بك! اختر من القائمة:", reply_markup=main_menu())

@dp.message(Reg.name)
async def get_name(msg: types.Message, state: FSMContext):
    cursor.execute("INSERT INTO users (user_id, name, balance) VALUES (?, ?, 0)", (msg.from_user.id, msg.text))
    db.commit()
    await msg.answer("تم التسجيل! ابدأ الآن.", reply_markup=main_menu())
    await state.clear()

# --- نظام الشحن ---
@dp.callback_query(F.data == "add_balance")
async def add_bal(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("أدخل المبلغ:")
    await state.set_state(Pay.amt)

@dp.message(Pay.amt)
async def get_amt(msg: types.Message, state: FSMContext):
    await state.update_data(amt=msg.text)
    await msg.answer("أرسل صورة الإيصال:")
    await state.set_state(Pay.photo)

@dp.message(Pay.photo, F.photo)
async def handle_photo(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    kb = types.InlineKeyboardMarkup(inline_keyboard=[[
        types.InlineKeyboardButton(text="✅ قبول", callback_data=f"app_{msg.from_user.id}_{data['amt']}"),
        types.InlineKeyboardButton(text="❌ رفض", callback_data=f"rej_{msg.from_user.id}")
    ]])
    await bot.send_photo(ADMIN_ID, msg.photo[-1].file_id, caption=f"طلب شحن من {msg.from_user.full_name}\nالمبلغ: {data['amt']}", reply_markup=kb)
    await msg.answer("جاري مراجعة الطلب.")
    await state.clear()

@dp.callback_query(F.data.startswith("app_"))
async def approve(call: types.CallbackQuery):
    _, uid, amt = call.data.split("_")
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amt, uid))
    db.commit()
    await call.message.edit_caption(caption="✅ تمت الإضافة.")
    await bot.send_message(uid, f"تم شحن {amt} جنيه.")

# --- نظام الخدمات (تمت إضافته) ---
@dp.callback_query(F.data == "show_services")
async def show_services(call: types.CallbackQuery):
    btns = [[types.InlineKeyboardButton(text=f"{v['name']} ({v['price']}ج)", callback_data=f"buy_{k}")] for k, v in SERVICES.items()]
    await call.message.edit_text("اختر الخدمة:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("buy_"))
async def start_buy(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(sid=call.data.split("_")[1])
    await call.message.answer("أدخل الكمية (مثال 1000):")
    await state.set_state(Order.qty)

@dp.message(Order.qty)
async def get_qty(msg: types.Message, state: FSMContext):
    await state.update_data(qty=msg.text)
    await msg.answer("أرسل الرابط:")
    await state.set_state(Order.link)

@dp.message(Order.link)
async def finish_buy(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    sid, qty = data['sid'], int(data['qty'])
    cost = (qty / 1000) * SERVICES[sid]['price']
    
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (msg.from_user.id,))
    bal = cursor.fetchone()[0]
    
    if bal >= cost:
        # كود تنفيذ الطلب (نفس كودك الأصلي)
        payload = {'key': API_KEY, 'action': 'add', 'service': sid, 'link': msg.text, 'quantity': qty}
        req = requests.post(SMMWIZ_URL, data=payload)
        if req.status_code == 200:
            cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (cost, msg.from_user.id))
            db.commit()
            await msg.answer("✅ تم تنفيذ طلبك!")
        else: await msg.answer("❌ فشل الاتصال.")
    else: await msg.answer("❌ رصيد غير كافٍ!")
    await state.clear()

async def main(): await dp.start_polling(bot)
if __name__ == "__main__": asyncio.run(main())
