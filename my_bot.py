import sqlite3
import requests
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = "8960056224:AAEeYf2SxBa9rfyUEzEnLEf2HGIK5K1Pfrw"
API_KEY = "3ea10a856b380134944184dfd394454c"
ADMIN_ID = 8201315070
SMMWIZ_URL = "https://smmwiz.com/api/v2"

PRICES = {"followers": 35, "likes": 20, "views": 6}
SERVICES = {
    "17678": {"name": "متابعين انستقرام", "price": PRICES["followers"]},
    "17333": {"name": "متابعين فيسبوك", "price": PRICES["followers"]},
    "20216": {"name": "لايكات انستقرام", "price": PRICES["likes"]},
    "11775": {"name": "لايكات تيك توك", "price": PRICES["likes"]},
    "2981":  {"name": "لايكات فيسبوك", "price": PRICES["likes"]},
    "19968": {"name": "مشاهدات تيك توك", "price": PRICES["views"]},
    "14245": {"name": "مشاهدات انستقرام", "price": PRICES["views"]},
}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage()) # ضروري جداً لمنع توقف البوت
db = sqlite3.connect("store.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, balance REAL DEFAULT 0)")
db.commit()

class OrderStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_quantity = State()
    waiting_for_link = State()
    waiting_for_amount = State()
    waiting_for_photo = State()

def main_menu():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🛒 شراء خدمات", callback_data="show_services")],
        [types.InlineKeyboardButton(text="💰 شحن الرصيد", callback_data="add_balance")],
        [types.InlineKeyboardButton(text="💳 رصيدي", callback_data="check_balance")]
    ])

@dp.message(Command("start"))
async def start(msg: types.Message, state: FSMContext):
    cursor.execute("SELECT name FROM users WHERE user_id=?", (msg.from_user.id,))
    if not cursor.fetchone():
        await msg.answer("أهلاً بك في Tik Wolf! 🐺 اكتب اسمك للبدء:")
        await state.set_state(OrderStates.waiting_for_name)
    else:
        await msg.answer("مرحباً بك مجدداً! اختر من القائمة:", reply_markup=main_menu())

@dp.message(OrderStates.waiting_for_name)
async def get_name(msg: types.Message, state: FSMContext):
    cursor.execute("INSERT INTO users (user_id, name, balance) VALUES (?, ?, 0)", (msg.from_user.id, msg.text))
    db.commit()
    await msg.answer("تم حفظ بياناتك! استخدم القائمة:", reply_markup=main_menu())
    await state.clear()

@dp.callback_query(F.data == "check_balance")
async def check_balance(call: types.CallbackQuery):
    await call.answer()
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (call.from_user.id,))
    row = cursor.fetchone()
    await call.message.answer(f"رصيدك الحالي: {row[0] if row else 0} جنيه.")

@dp.callback_query(F.data == "add_balance")
async def add_balance(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("💰 أدخل المبلغ الذي حولته:")
    await state.set_state(OrderStates.waiting_for_amount)

@dp.message(OrderStates.waiting_for_amount)
async def get_amount(msg: types.Message, state: FSMContext):
    await state.update_data(amount=msg.text)
    await msg.answer("✅ تمام، أرسل سكرين شوت التحويل الآن:")
    await state.set_state(OrderStates.waiting_for_photo)

@dp.message(OrderStates.waiting_for_photo, F.photo)
async def handle_photo(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    amt = data.get('amount')
    kb = types.InlineKeyboardMarkup(inline_keyboard=[[
        types.InlineKeyboardButton(text="✅ قبول", callback_data=f"app_{msg.from_user.id}_{amt}"),
        types.InlineKeyboardButton(text="❌ رفض", callback_data=f"rej_{msg.from_user.id}")]])
    await bot.send_photo(ADMIN_ID, msg.photo[-1].file_id, caption=f"طلب إيداع من: {msg.from_user.full_name}\nالمبلغ: {amt}", reply_markup=kb)
    await msg.answer("تم إرسال الطلب للإدارة.")
    await state.clear()

@dp.callback_query(F.data.startswith("app_"))
async def approve(call: types.CallbackQuery):
    _, uid, amt = call.data.split("_")
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amt, uid))
    db.commit()
    await call.message.edit_caption(caption="✅ تمت الإضافة.")
    await bot.send_message(uid, f"🎉 تم شحن {amt} جنيه!")

@dp.callback_query(F.data == "show_services")
async def show_services(call: types.CallbackQuery):
    await call.answer()
    btns = [[types.InlineKeyboardButton(text=f"{i['name']} ({i['price']}ج)", callback_data=f"buy_{k}")] for k, i in SERVICES.items()]
    await call.message.edit_text("اختر الخدمة:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("buy_"))
async def buy(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await state.update_data(sid=call.data.split("_")[1])
    await call.message.answer("أدخل الكمية:")
    await state.set_state(OrderStates.waiting_for_quantity)

@dp.message(OrderStates.waiting_for_quantity)
async def get_qty(msg: types.Message, state: FSMContext):
    await state.update_data(qty=msg.text)
    await msg.answer("أرسل الرابط:")
    await state.set_state(OrderStates.waiting_for_link)

@dp.message(OrderStates.waiting_for_link)
async def finish(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    # كود تنفيذ الـ API والخصم هنا
    cursor.execute("SELECT name FROM users WHERE user_id=?", (msg.from_user.id,))
    name = cursor.fetchone()[0]
    await bot.send_message(ADMIN_ID, f"🛒 طلب جديد من {name}")
    await msg.answer("✅ تم التنفيذ!")
    await state.clear()

async def main(): await dp.start_polling(bot)
if __name__ == "__main__": asyncio.run(main())
