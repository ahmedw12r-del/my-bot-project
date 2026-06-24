import sqlite3
import requests
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# إعدادات البوت
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = "8960056224:AAEeYf2SxBa9rfyUEzEnLEf2HGIK5K1Pfrw"
API_KEY = "3ea10a856b380134944184dfd394454c"
ADMIN_ID = 8201315070
SMMWIZ_URL = "https://smmwiz.com/api/v2"

# الخدمات والأسعار
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
dp = Dispatcher(storage=MemoryStorage())
db = sqlite3.connect("store.db", check_same_thread=False)
cursor = db.cursor()
# إضافة عمود الاسم لجدول المستخدمين
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, balance REAL DEFAULT 0)")
db.commit()

class OrderStates(StatesGroup):
    waiting_for_name = State() # للتسجيل
    waiting_for_quantity = State()
    waiting_for_link = State()
    waiting_for_amount = State()

def main_menu():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🛒 شراء خدمات", callback_data="show_services")],
        [types.InlineKeyboardButton(text="💰 شحن الرصيد", callback_data="add_balance")],
        [types.InlineKeyboardButton(text="💳 رصيدي", callback_data="check_balance")]
    ])

@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT name FROM users WHERE user_id=?", (message.from_user.id,))
    user = cursor.fetchone()
    if not user:
        await message.answer("أهلاً بك في Tik Wolf! 🐺 من فضلك اكتب اسمك للبدء:")
        await state.set_state(OrderStates.waiting_for_name)
    else:
        await message.answer(f"أهلاً بك مجدداً {user[0]}! اختر من القائمة:", reply_markup=main_menu())

@dp.message(OrderStates.waiting_for_name)
async def get_name(msg: types.Message, state: FSMContext):
    cursor.execute("INSERT INTO users (user_id, name, balance) VALUES (?, ?, 0)", (msg.from_user.id, msg.text))
    db.commit()
    await msg.answer("تم تسجيلك بنجاح! اختر الخدمة من القائمة:", reply_markup=main_menu())
    await state.clear()

# --- نظام الشحن (المبلغ + الصورة) ---
@dp.callback_query(F.data == "add_balance")
async def add_balance(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("💰 يرجى إدخال المبلغ الذي ستقوم بتحويله:")
    await state.set_state(OrderStates.waiting_for_amount)

@dp.message(OrderStates.waiting_for_amount)
async def get_amount(msg: types.Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("رقم فقط!")
    await state.update_data(amount=msg.text)
    await msg.answer("✅ الآن أرسل صورة إيصال التحويل للمراجعة:")

@dp.message(F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    amount = data.get('amount')
    if not amount: return await message.answer("أدخل المبلغ أولاً!")
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ قبول وشحن", callback_data=f"approve_{message.from_user.id}_{amount}"),
         types.InlineKeyboardButton(text="❌ رفض", callback_data=f"reject_{message.from_user.id}")]
    ])
    await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, 
                         caption=f"💸 إيداع جديد\nمن: {message.from_user.full_name}\nالمبلغ: {amount} ج", 
                         reply_markup=keyboard)
    await message.answer("تم إرسال الإيصال للإدارة للمراجعة.")
    await state.clear()

@dp.callback_query(F.data.startswith("approve_"))
async def approve_payment(call: types.CallbackQuery):
    _, uid, amt = call.data.split("_")
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amt, uid))
    db.commit()
    await call.message.edit_caption(caption=f"✅ تم القبول وشحن {amt} للمستخدم.")
    await bot.send_message(uid, f"🎉 مبروك! تم شحن {amt} جنيه لرصيدك.")

# --- نظام الشراء (مع التنبيه للأدمن) ---
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
    s_id = data['service_id']
    total_price = (qty / 1000) * SERVICES[s_id]['price']
    await state.update_data(qty=qty, total_price=total_price)
    await msg.answer(f"💰 التكلفة: {total_price} ج. أرسل الرابط:")
    await state.set_state(OrderStates.waiting_for_link)

@dp.message(OrderStates.waiting_for_link)
async def confirm_order(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    cursor.execute("SELECT name, balance FROM users WHERE user_id=?", (msg.from_user.id,))
    user = cursor.fetchone()
    
    if user[1] >= data['total_price']:
        payload = {'key': API_KEY, 'action': 'add', 'service': data['service_id'], 'link': msg.text, 'quantity': data['qty']}
        req = requests.post(SMMWIZ_URL, data=payload)
        if req.status_code == 200:
            cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (data['total_price'], msg.from_user.id))
            db.commit()
            # التنبيه الذي طلبته
            await bot.send_message(ADMIN_ID, f"🛒 عملية شراء جديدة!\n👤 العميل: {user[0]}\n📦 الخدمة: {SERVICES[data['service_id']]['name']}\n💰 المبلغ: {data['total_price']} ج\nرصيده المتبقي: {user[1]-data['total_price']} ج")
            await msg.answer("✅ تم تنفيذ طلبك بنجاح!")
        else: await msg.answer("❌ فشل الاتصال بالسيرفر.")
    else: await msg.answer("❌ رصيد غير كافٍ!")
    await state.clear()

async def main(): await dp.start_polling(bot)
if __name__ == "__main__": asyncio.run(main())
