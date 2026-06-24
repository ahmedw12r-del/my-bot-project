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
dp = Dispatcher(storage=MemoryStorage())
db = sqlite3.connect("store.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0)")
db.commit()

class OrderStates(StatesGroup):
    waiting_for_quantity = State()
    waiting_for_link = State()
    waiting_for_amount = State()
    waiting_for_photo = State() # حالة جديدة لاستقبال الصورة

# --- القوائم ---
def main_menu():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🛒 شراء خدمات", callback_data="show_services")],
        [types.InlineKeyboardButton(text="💰 شحن", callback_data="add_balance")],
        [types.InlineKeyboardButton(text="💳 رصيدي", callback_data="check_balance")]
    ])

# --- الشحن (الخطوة 1: المبلغ) ---
@dp.callback_query(F.data == "add_balance")
async def start_add_balance(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("💰 أدخل المبلغ الذي قمت بتحويله:")
    await state.set_state(OrderStates.waiting_for_amount)

@dp.message(OrderStates.waiting_for_amount)
async def get_amount(msg: types.Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("أدخل أرقام فقط!")
    await state.update_data(amount=msg.text)
    await msg.answer("✅ تمام، الآن أرسل صورة الإيصال (سكرين شوت):")
    await state.set_state(OrderStates.waiting_for_photo) # الانتقال لحالة انتظار الصورة

# --- الشحن (الخطوة 2: الصورة) ---
@dp.message(OrderStates.waiting_for_photo, F.photo)
async def handle_photo(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    amount = data.get('amount')
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ قبول وشحن", callback_data=f"approve_{msg.from_user.id}_{amount}"),
         types.InlineKeyboardButton(text="❌ رفض", callback_data=f"reject_{msg.from_user.id}")]
    ])
    
    # إرسال الصورة للأدمن
    await bot.send_photo(ADMIN_ID, msg.photo[-1].file_id, 
                         caption=f"💸 إيداع جديد من: {msg.from_user.full_name}\nالمبلغ: {amount} ج", 
                         reply_markup=keyboard)
    
    await msg.answer("⏳ تم استلام الصورة، جاري مراجعتها من قبل الإدارة.")
    await state.clear()

# --- معالجة الإدارة ---
@dp.callback_query(F.data.startswith("approve_"))
async def approve_payment(call: types.CallbackQuery):
    _, uid, amt = call.data.split("_")
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amt, uid))
    db.commit()
    await call.message.edit_caption(caption=f"✅ تم القبول وشحن {amt} للمستخدم.")
    await bot.send_message(uid, f"🎉 مبروك! تم شحن {amt} جنيه لرصيدك.")

# --- باقي كود الشراء (لا تغيير) ---
@dp.message(Command("start"))
async def start(message: types.Message):
    cursor.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0)", (message.from_user.id,))
    db.commit()
    await message.answer("أهلاً بك في Tik Wolf! 🐺 اختر من القائمة:", reply_markup=main_menu())

@dp.callback_query(F.data == "show_services")
async def show_services(call: types.CallbackQuery):
    buttons = [[types.InlineKeyboardButton(text=f"{info['name']} ({info['price']} ج)", callback_data=f"buy_{s_id}")] for s_id, info in SERVICES.items()]
    await call.message.edit_text("اختر الخدمة:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(service_id=call.data.split("_")[1])
    await call.message.answer("أدخل الكمية:")
    await state.set_state(OrderStates.waiting_for_quantity)

@dp.message(OrderStates.waiting_for_quantity)
async def get_qty(msg: types.Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("رقم فقط!")
    qty = int(msg.text)
    data = await state.get_data()
    total_price = (qty / 1000) * SERVICES[data['service_id']]['price']
    await state.update_data(qty=qty, total_price=total_price)
    await msg.answer("أرسل الرابط:")
    await state.set_state(OrderStates.waiting_for_link)

@dp.message(OrderStates.waiting_for_link)
async def confirm_order(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (msg.from_user.id,))
    res = cursor.fetchone()
    if res and res[0] >= data['total_price']:
        payload = {'key': API_KEY, 'action': 'add', 'service': data['service_id'], 'link': msg.text, 'quantity': data['qty']}
        req = requests.post(SMMWIZ_URL, data=payload)
        if req.status_code == 200:
            cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (data['total_price'], msg.from_user.id))
            db.commit()
            await msg.answer("✅ تم التنفيذ!")
        else: await msg.answer("❌ خطأ.")
    else: await msg.answer("❌ رصيد غير كافٍ!")
    await state.clear()

async def main(): await dp.start_polling(bot)
if __name__ == "__main__": asyncio.run(main())
