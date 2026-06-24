import sqlite3
import requests
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

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
dp = Dispatcher()
db = sqlite3.connect("store.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0)")
db.commit()

class OrderStates(StatesGroup):
    waiting_for_quantity = State()
    waiting_for_link = State()
    waiting_for_amount = State() # جديدة للشحن

def main_menu():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🛒 شراء خدمات", callback_data="show_services")],
        [types.InlineKeyboardButton(text="💰 شحن الرصيد", callback_data="add_balance")],
        [types.InlineKeyboardButton(text="💳 رصيدي", callback_data="check_balance")]
    ])

@dp.message(Command("start"))
async def start(message: types.Message):
    cursor.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0)", (message.from_user.id,))
    db.commit()
    await message.answer("أهلاً بك في Tik Wolf! 🐺 اختر من القائمة:", reply_markup=main_menu())

@dp.callback_query(F.data == "show_services")
async def show_services(call: types.CallbackQuery):
    await call.answer()
    buttons = [[types.InlineKeyboardButton(text=f"{info['name']} ({info['price']} ج)", callback_data=f"buy_{s_id}")] for s_id, info in SERVICES.items()]
    buttons.append([types.InlineKeyboardButton(text="🔙 رجوع", callback_data="back")])
    await call.message.edit_text("اختر الخدمة (السعر للـ 1000):", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data == "back")
async def back(call: types.CallbackQuery):
    await call.message.edit_text("أهلاً بك في Tik Wolf! 🐺 اختر من القائمة:", reply_markup=main_menu())

@dp.callback_query(F.data == "check_balance")
async def check_balance(call: types.CallbackQuery):
    await call.answer()
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (call.from_user.id,))
    row = cursor.fetchone()
    bal = row[0] if row else 0
    await call.message.answer(f"رصيدك الحالي: {bal} جنيه.")

# --- نظام الشحن الجديد ---
@dp.callback_query(F.data == "add_balance")
async def add_balance(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.answer("💰 يرجى إدخال المبلغ الذي ستقوم بتحويله:")
    await state.set_state(OrderStates.waiting_for_amount)

@dp.message(OrderStates.waiting_for_amount)
async def get_amount(msg: types.Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("من فضلك أدخل رقماً فقط.")
    await state.update_data(amount=msg.text)
    await msg.answer("✅ تمام، الآن أرسل صورة إيصال التحويل للمراجعة:")
    # ننتظر الصورة في دالة handle_photo

@dp.message(F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    amount = data.get('amount')
    
    if amount:
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="✅ قبول", callback_data=f"approve_{message.from_user.id}_{amount}"),
             types.InlineKeyboardButton(text="❌ رفض", callback_data=f"reject_{message.from_user.id}")]
        ])
        await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"💸 إيداع جديد\nمن: {message.from_user.full_name}\nالمبلغ: `{amount} ج`", reply_markup=keyboard)
        await message.answer("تم إرسال الإيصال للإدارة للمراجعة.")
        await state.clear()
    else:
        await message.answer("يرجى اختيار 'شحن الرصيد' من القائمة أولاً.")

@dp.callback_query(F.data.startswith("approve_"))
async def approve_payment(call: types.CallbackQuery):
    _, user_id, amount = call.data.split("_")
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    db.commit()
    await call.message.edit_caption(caption=f"✅ تم القبول وإضافة {amount} جنيه.")
    await bot.send_message(user_id, f"🎉 مبروك! تمت إضافة {amount} جنيه لرصيدك.")

@dp.callback_query(F.data.startswith("reject_"))
async def reject_payment(call: types.CallbackQuery):
    _, user_id = call.data.split("_")
    await call.message.edit_caption(caption="❌ تم رفض الطلب.")
    await bot.send_message(user_id, "⚠️ عذراً، تم رفض إيصالك. يرجى مراجعة الإدارة.")

# --- الشراء ---
@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(call: types.CallbackQuery, state: FSMContext):
    await call.answer()
    s_id = call.data.split("_")[1]
    await state.update_data(service_id=s_id)
    await call.message.answer("أدخل الكمية المطلوبة:")
    await state.set_state(OrderStates.waiting_for_quantity)

@dp.message(OrderStates.waiting_for_quantity)
async def get_qty(msg: types.Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("رقم فقط!")
    qty = int(msg.text)
    data = await state.get_data()
    s_id = data['service_id']
    total_price = (qty / 1000) * SERVICES[s_id]['price']
    await state.update_data(qty=qty, total_price=total_price)
    await msg.answer(f"💰 التكلفة الإجمالية: {total_price} ج. أرسل الرابط للتنفيذ:")
    await state.set_state(OrderStates.waiting_for_link)

@dp.message(OrderStates.waiting_for_link)
async def confirm_order(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    cursor.execute("SELECT balance FROM users WHERE user_id=?", (msg.from_user.id,))
    res = cursor.fetchone()
    if res and res[0] >= data['total_price']:
        payload = {'key': API_KEY, 'action': 'add', 'service': data['service_id'], 'link': msg.text, 'quantity': data['qty']}
        try:
            req = requests.post(SMMWIZ_URL, data=payload)
            if req.status_code == 200:
                cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (data['total_price'], msg.from_user.id))
                db.commit()
                await msg.answer("✅ تم التنفيذ بنجاح!")
            else: await msg.answer("❌ خطأ في الاتصال.")
        except: await msg.answer("❌ حدث خطأ.")
    else: await msg.answer("❌ رصيدك غير كافٍ!")
    await state.clear()

@dp.message(Command("add"))
async def admin_add(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        args = message.text.split()
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (args[2], args[1]))
        db.commit()
        await message.answer(f"✅ تم إضافة {args[2]} للمستخدم {args[1]}")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
