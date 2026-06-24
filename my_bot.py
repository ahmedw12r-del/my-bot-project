import sqlite3
import requests
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# إعداد السجلات
logging.basicConfig(level=logging.INFO)

# --- التعريفات الثابتة ---
BOT_TOKEN = "8960056224:AAEeYf2SxBa9rfyUEzEnLEf2HGIK5K1Pfrw"
API_KEY = "e20891c4d8d4db32fc1bc53f173c0f1e"
ADMIN_ID = 8201315070
SMMWIZ_URL = "https://smmwiz.com/api/v2"

# إعدادات الخدمة والأسعار
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

# تهيئة البوت وقاعدة البيانات
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db = sqlite3.connect("store.db", check_same_thread=False)
cursor = db.cursor()
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

# --- الأوامر الأساسية ---
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

# --- الشحن اليدوي ---
@dp.callback_query(F.data == "add_balance")
async def add_balance(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("💰 يرجى إدخال المبلغ الذي قمت بتحويله:")
    await state.set_state(PaymentStates.waiting_for_amount)

@dp.message(PaymentStates.waiting_for_amount)
async def get_amount(msg: types.Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("من فضلك أدخل رقماً فقط.")
    await state.update_data(amount=msg.text)
    await msg.answer("✅ الآن أرسل صورة إيصال التحويل (سكرين شوت):")
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
                         caption=f"💸 طلب شحن جديد\nالاسم: {message.from_user.full_name}\nID: `{message.from_user.id}`\nالمبلغ: `{amount} ج`",
                         reply_markup=keyboard)
    await message.answer("تم إرسال طلب الشحن للإدارة.")
    await state.clear()

# --- التعامل مع أزرار الأدمن ---
@dp.callback_query(F.data.startswith("approve_"))
async def approve_payment(call: types.CallbackQuery):
    _, user_id, amount = call.data.split("_")
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    db.commit()
    await call.message.edit_caption(caption=f"✅ تم القبول وإضافة {amount} ج.")
    await bot.send_message(user_id, f"🎉 مبروك! تمت إضافة {amount} جنيه لرصيدك.")

@dp.callback_query(F.data.startswith("reject_"))
async def reject_payment(call: types.CallbackQuery):
    _, user_id = call.data.split("_")
    await call.message.edit_caption(caption="❌ تم الرفض.")
    await bot.send_message(user_id, "⚠️ عذراً، تم رفض إيصالك.")

# --- الشراء وتنبيه الإدارة ---
@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(call: types.CallbackQuery, state: FSMContext):
    s_id = call.data.split("_")[1]
    await state.update_data(service_id=s_id)
    await call.message.answer("أدخل الكمية:")
    await state.set_state(OrderStates.waiting_for_quantity)

@dp.message(OrderStates.waiting_for_quantity)
async def get_qty(msg: types.Message, state: FSMContext):
    qty = int(msg.text)
    data = await state.get_data()
    total_price = (qty / 1000) * SERVICES[data['service_id']]['price']
    await state.update_data(qty=qty, total_price=total_price)
    await msg.answer(f"💰 التكلفة: {total_price} ج. أرسل الرابط:")
    await state.set_state(OrderStates.waiting_for_link)

@dp.message(OrderStates.waiting_for_link)
async def confirm_order(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    cursor.execute("SELECT name, balance FROM users WHERE user_id=?", (msg.from_user.id,))
    user_info = cursor.fetchone()
    if user_info and user_info[1] >= data['total_price']:
        # تنفيذ الطلب (أضف كود API هنا)
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (data['total_price'], msg.from_user.id))
        db.commit()
        await bot.send_message(ADMIN_ID, f"🛒 شراء جديد!\n👤: {user_info[0]}\n📦: {SERVICES[data['service_id']]['name']}\n💰: {data['total_price']} ج\n💳 المتبقي: {user_info[1]-data['total_price']} ج")
        await msg.answer("✅ تم تنفيذ طلبك!")
    else: await msg.answer("❌ رصيدك غير كافٍ!")
    await state.clear()

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
