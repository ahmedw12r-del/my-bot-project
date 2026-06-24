import sqlite3
import requests
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# إعداد السجلات
logging.basicConfig(level=logging.INFO)

# --- التعريفات ---
BOT_TOKEN = "8960056224:AAEeYf2SxBa9rfyUEzEnLEf2HGIK5K1Pfrw"
API_KEY = "e20891c4d8d4db32fc1bc53f173c0f1e"
ADMIN_ID = 8201315070
SMMWIZ_URL = "https://smmwiz.com/api/v2"

# تهيئة البوت وقاعدة البيانات
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db = sqlite3.connect("store.db", check_same_thread=False)
cursor = db.cursor()
# إضافة عمود name
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, balance REAL DEFAULT 0)")
db.commit()

# --- الحالات (States) ---
class OrderStates(StatesGroup):
    waiting_for_quantity = State()
    waiting_for_link = State()

class Registration(StatesGroup):
    waiting_for_name = State()

class PaymentStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_photo = State()

# --- القوائم ---
def main_menu():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🛒 شراء خدمات", callback_data="show_services")],
        [types.InlineKeyboardButton(text="💰 شحن الرصيد", callback_data="add_balance")],
        [types.InlineKeyboardButton(text="💳 رصيدي", callback_data="check_balance")]
    ])

# --- الدوال ---
@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT name FROM users WHERE user_id=?", (message.from_user.id,))
    user = cursor.fetchone()
    if not user:
        await message.answer("أهلاً بك في Tik Wolf! 🐺\nيرجى كتابة اسمك للبدء:")
        await state.set_state(Registration.waiting_for_name)
    else:
        await message.answer(f"أهلاً بك مجدداً {user[0]}! اختر من القائمة:", reply_markup=main_menu())

@dp.message(Registration.waiting_for_name)
async def get_name(msg: types.Message, state: FSMContext):
    cursor.execute("INSERT INTO users (user_id, name, balance) VALUES (?, ?, 0)", (msg.from_user.id, msg.text))
    db.commit()
    await msg.answer("تم حفظ بياناتك بنجاح! اختر من القائمة:", reply_markup=main_menu())
    await state.clear()

@dp.callback_query(F.data == "add_balance")
async def add_balance(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("💰 يرجى إدخال المبلغ الذي ستقوم بتحويله:")
    await state.set_state(PaymentStates.waiting_for_amount)

@dp.message(PaymentStates.waiting_for_amount)
async def get_amount(msg: types.Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("من فضلك أدخل رقماً فقط.")
    await state.update_data(amount=msg.text)
    await msg.answer("✅ تمام، الآن أرسل صورة إيصال التحويل للمراجعة:")
    await state.set_state(PaymentStates.waiting_for_photo)

@dp.message(PaymentStates.waiting_for_photo, F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    amount = data['amount']
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ قبول", callback_data=f"approve_{message.from_user.id}_{amount}"),
         types.InlineKeyboardButton(text="❌ رفض", callback_data=f"reject_{message.from_user.id}")]
    ])
    
    await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, 
                         caption=f"💸 طلب شحن جديد\nالاسم: {message.from_user.full_name}\nالمبلغ: {amount} ج",
                         reply_markup=keyboard)
    await message.answer("تم إرسال الطلب للإدارة.")
    await state.clear()

@dp.callback_query(F.data.startswith("approve_"))
async def approve_payment(call: types.CallbackQuery):
    _, user_id, amount = call.data.split("_")
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    db.commit()
    await call.message.edit_caption(caption=f"✅ تم القبول وإضافة {amount} جنيه.")
    await bot.send_message(user_id, f"🎉 مبروك! تمت إضافة {amount} جنيه لرصيدك.")

# --- بقية دوال الشراء (نفس كودك مع تعديل التنبيه) ---
@dp.message(OrderStates.waiting_for_link)
async def confirm_order(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    cursor.execute("SELECT name, balance FROM users WHERE user_id=?", (msg.from_user.id,))
    user_data = cursor.fetchone()
    if user_data and user_data[1] >= data['total_price']:
        # هنا يتم تنفيذ الطلب (أضف كود الـ API الخاص بك هنا)
        new_bal = user_data[1] - data['total_price']
        cursor.execute("UPDATE users SET balance = ? WHERE user_id=?", (new_bal, msg.from_user.id))
        db.commit()
        await bot.send_message(ADMIN_ID, f"🛒 عملية شراء جديدة!\n👤 العميل: {user_data[0]}\n💰 دفع: {data['total_price']} ج")
        await msg.answer("✅ تم تنفيذ طلبك!")
    else:
        await msg.answer("❌ رصيد غير كافٍ!")
    await state.clear()

# تشغيل البوت
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
