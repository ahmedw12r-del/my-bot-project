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

# --- الإعدادات الأساسية ---
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = "8960056224:AAEeYf2SxBa9rfyUEzEnLEf2HGIK5K1Pfrw"
API_KEY = "3ea10a856b380134944184dfd394454c"
ADMIN_ID = 8201315070
SMMWIZ_URL = "https://smmwiz.com/api/v2"

# --- هيكلة الخدمات بالتصنيفات ---
CATEGORIES = {
    "insta": {"name": "📸 انستجرام", "services": {"17678": "متابعين", "20216": "لايكات", "14245": "مشاهدات"}},
    "fb": {"name": "🔵 فيسبوك", "services": {"17333": "متابعين", "2981": "لايكات"}},
    "tiktok": {"name": "🎵 تيك توك", "services": {"11775": "لايكات", "19968": "مشاهدات"}}
}

# --- تهيئة البوت وقاعدة البيانات ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db = sqlite3.connect("store.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, balance REAL DEFAULT 0)")
db.commit()

# --- الحالات ---
class UserStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_amount = State()
    waiting_for_photo = State()
    waiting_for_quantity = State()
    waiting_for_link = State()

# --- دالة القائمة الرئيسية ---
def main_menu():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🛒 شراء خدمات", callback_data="categories")],
        [types.InlineKeyboardButton(text="💰 شحن الرصيد", callback_data="add_balance")],
        [types.InlineKeyboardButton(text="💳 رصيدي", callback_data="check_balance")]
    ])

@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT name FROM users WHERE user_id=?", (message.from_user.id,))
    user = cursor.fetchone()
    if not user:
        await message.answer("أهلاً بك في Tik Wolf! 🐺 اكتب اسمك للبدء:")
        await state.set_state(UserStates.waiting_for_name)
    else:
        await message.answer(f"مرحباً بك مجدداً {user[0]}!", reply_markup=main_menu())

@dp.message(UserStates.waiting_for_name)
async def set_name(message: types.Message, state: FSMContext):
    cursor.execute("INSERT INTO users (user_id, name, balance) VALUES (?, ?, 0)", (message.from_user.id, message.text))
    db.commit()
    await message.answer("تم حفظ بياناتك!", reply_markup=main_menu())
    await state.clear()

# --- إدارة التصنيفات والخدمات ---
@dp.callback_query(F.data == "categories")
async def show_categories(call: types.CallbackQuery):
    btns = [[types.InlineKeyboardButton(text=v['name'], callback_data=f"cat_{k}")] for k, v in CATEGORIES.items()]
    btns.append([types.InlineKeyboardButton(text="🔙 رجوع", callback_data="main_menu")])
    await call.message.edit_text("اختر المنصة:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("cat_"))
async def show_services(call: types.CallbackQuery):
    cat_id = call.data.split("_")[1]
    btns = [[types.InlineKeyboardButton(text=v, callback_data=f"buy_{k}")] for k, v in CATEGORIES[cat_id]['services'].items()]
    btns.append([types.InlineKeyboardButton(text="🔙 للوراء", callback_data="categories")])
    await call.message.edit_text(f"خدمات {CATEGORIES[cat_id]['name']}:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=btns))

# --- الشحن اليدوي ---
@dp.callback_query(F.data == "add_balance")
async def add_balance(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("💰 أدخل المبلغ الذي حولته:")
    await state.set_state(UserStates.waiting_for_amount)

@dp.message(UserStates.waiting_for_amount)
async def get_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("أرقام فقط!")
    await state.update_data(amount=message.text)
    await message.answer("✅ أرسل سكرين شوت التحويل:")
    await state.set_state(UserStates.waiting_for_photo)

@dp.message(UserStates.waiting_for_photo, F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    amt = data.get('amount')
    kb = types.InlineKeyboardMarkup(inline_keyboard=[[
        types.InlineKeyboardButton(text="✅ قبول", callback_data=f"app_{message.from_user.id}_{amt}"),
        types.InlineKeyboardButton(text="❌ رفض", callback_data=f"rej_{message.from_user.id}")]])
    await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"💸 إيداع: {amt} ج\nمن: {message.from_user.full_name}", reply_markup=kb)
    await message.answer("تم الإرسال للإدارة.")
    await state.clear()

@dp.callback_query(F.data.startswith("app_"))
async def approve(call: types.CallbackQuery):
    _, uid, amt = call.data.split("_")
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amt, uid))
    db.commit()
    await call.message.edit_caption(caption="✅ تمت الموافقة.")
    await bot.send_message(uid, f"🎉 تم شحن {amt} جنيه!")

# --- إتمام الشراء ---
@dp.callback_query(F.data.startswith("buy_"))
async def buy_service(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(sid=call.data.split("_")[1])
    await call.message.answer("أدخل الكمية:")
    await state.set_state(UserStates.waiting_for_quantity)

@dp.message(UserStates.waiting_for_quantity)
async def get_qty(msg: types.Message, state: FSMContext):
    await state.update_data(qty=int(msg.text))
    await msg.answer("أرسل الرابط:")
    await state.set_state(UserStates.waiting_for_link)

@dp.message(UserStates.waiting_for_link)
async def finish(msg: types.Message, state: FSMContext):
    if not re.match(r'https?://', msg.text): return await msg.answer("رابط غير صحيح!")
    data = await state.get_data()
    # إضافة المنطق البرمجي للخصم والتنفيذ...
    await bot.send_message(ADMIN_ID, f"🛒 طلب جديد من {msg.from_user.full_name}\nالكمية: {data['qty']}")
    await msg.answer("✅ تم التنفيذ!")
    await state.clear()

@dp.callback_query(F.data == "main_menu")
async def main_menu_cb(call: types.CallbackQuery):
    await call.message.edit_text("القائمة الرئيسية:", reply_markup=main_menu())

@dp.callback_query(F.data == "check_balance")
async def check_balance(call: types.CallbackQuery):
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (call.from_user.id,))
    bal = cursor.fetchone()
    await call.message.answer(f"رصيدك: {bal[0] if bal else 0} ج.")

async def main(): 
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__": 
    asyncio.run(main())
