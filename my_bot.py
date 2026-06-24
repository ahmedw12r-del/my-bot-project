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

# --- هيكلة الخدمات والأسعار ---
CATEGORIES = {
    "insta": {
        "name": "📸 انستجرام",
        "services": {
            "17678": {"name": "متابعين", "price": 35},
            "20216": {"name": "لايكات", "price": 20},
            "14245": {"name": "مشاهدات", "price": 6}
        }
    },
    "fb": {
        "name": "🔵 فيسبوك",
        "services": {
            "17333": {"name": "متابعين", "price": 35},
            "2981": {"name": "لايكات", "price": 20}
        }
    },
    "tiktok": {
        "name": "🎵 تيك توك",
        "services": {
            "11775": {"name": "لايكات", "price": 20},
            "19968": {"name": "مشاهدات", "price": 6}
        }
    }
}

# --- تهيئة البوت وقاعدة البيانات ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db = sqlite3.connect("store.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, balance REAL DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, user_id INTEGER, status TEXT)")
db.commit()

# --- الحالات (States) ---
class UserStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_amount = State()
    waiting_for_photo = State()
    waiting_for_quantity = State()
    waiting_for_link = State()

# --- نظام مراقبة الطلبات التلقائي ---
async def check_order_status():
    while True:
        cursor.execute("SELECT order_id, user_id FROM orders WHERE status != 'Completed'")
        orders = cursor.fetchall()
        for o_id, u_id in orders:
            try:
                req = requests.post(SMMWIZ_URL, data={'key': API_KEY, 'action': 'status', 'order': o_id})
                if req.status_code == 200:
                    status = req.json().get('status')
                    if status == 'Pending':
                        await bot.send_message(u_id, "⏳ طلبك قيد الانتظار، انتظر دقيقتين حتى يتم التنفيذ.")
                    elif status == 'In Progress':
                        cursor.execute("UPDATE orders SET status = 'Completed' WHERE order_id = ?", (o_id,))
                        db.commit()
                        await bot.send_message(u_id, "🚀 جاري تنفيذ طلبك الآن! سيكتمل خلال 5 دقائق.")
            except Exception as e:
                logging.error(f"Error checking status: {e}")
        await asyncio.sleep(120) # فحص كل دقيقتين

# --- القائمة الرئيسية ---
def main_menu():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🛒 شراء خدمات", callback_data="categories")],
        [types.InlineKeyboardButton(text="💰 شحن الرصيد", callback_data="add_balance")],
        [types.InlineKeyboardButton(text="💳 لوحة التحكم (رصيدي)", callback_data="check_balance")]
    ])

# --- بداية البوت ---
@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT name FROM users WHERE user_id=?", (message.from_user.id,))
    user = cursor.fetchone()
    if not user:
        await message.answer("أهلاً بك في Tik Wolf! 🐺 من فضلك اكتب اسمك للبدء:")
        await state.set_state(UserStates.waiting_for_name)
    else:
        await message.answer(f"أهلاً بك يا {user[0]}! اختر ما تريد من القائمة:", reply_markup=main_menu())

@dp.message(UserStates.waiting_for_name)
async def set_name(message: types.Message, state: FSMContext):
    cursor.execute("INSERT INTO users (user_id, name, balance) VALUES (?, ?, 0)", (message.from_user.id, message.text))
    db.commit()
    await message.answer("تم حفظ بياناتك بنجاح!", reply_markup=main_menu())
    await state.clear()

# --- لوحة التحكم (Dashboard) ---
@dp.callback_query(F.data == "check_balance")
async def show_dashboard(call: types.CallbackQuery):
    cursor.execute("SELECT name, balance FROM users WHERE user_id=?", (call.from_user.id,))
    user = cursor.fetchone()
    name, bal = user if user else ("غير مسجل", 0)
    dashboard = (
        f"📊  **لوحة تحكم المستخدم**\n"
        f"━━━━━━━━━━━━━━━\n\n"
        f"👤  الاسم:   {name}\n\n"
        f"💰  الرصيد:   {bal}  ج.م\n\n"
        f"🆔  الرقم التعريفي:   {call.from_user.id}\n\n"
        f"━━━━━━━━━━━━━━━"
    )
    await call.message.edit_text(dashboard, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="main_menu")]
    ]))

# --- إدارة الخدمات ---
@dp.callback_query(F.data == "categories")
async def show_categories(call: types.CallbackQuery):
    btns = [[types.InlineKeyboardButton(text=v['name'], callback_data=f"cat_{k}")] for k, v in CATEGORIES.items()]
    btns.append([types.InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="main_menu")])
    await call.message.edit_text("اختر المنصة:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("cat_"))
async def show_services(call: types.CallbackQuery):
    cat_id = call.data.split("_")[1]
    btns = [[types.InlineKeyboardButton(text=f"{v['name']} ({v['price']}ج للـ 1000)", callback_data=f"buy_{cat_id}_{sid}")] for sid, v in CATEGORIES[cat_id]['services'].items()]
    btns.append([types.InlineKeyboardButton(text="🔙 رجوع", callback_data="categories")])
    await call.message.edit_text(f"خدمات {CATEGORIES[cat_id]['name']}:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=btns))

# --- نظام الشحن ---
@dp.callback_query(F.data == "add_balance")
async def add_balance(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("كم المبلغ الذي تريد تحويله؟ (أدخل الرقم فقط):")
    await state.set_state(UserStates.waiting_for_amount)

@dp.message(UserStates.waiting_for_amount)
async def get_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("يرجى إدخال أرقام فقط!")
    await state.update_data(amount=message.text)
    await message.answer("✅ تمام، أرسل سكرين شوت التحويل الآن للمراجعة:")
    await state.set_state(UserStates.waiting_for_photo)

@dp.message(UserStates.waiting_for_photo, F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    amt = data.get('amount')
    kb = types.InlineKeyboardMarkup(inline_keyboard=[[
        types.InlineKeyboardButton(text="✅ قبول", callback_data=f"app_{message.from_user.id}_{amt}"),
        types.InlineKeyboardButton(text="❌ رفض", callback_data=f"rej_{message.from_user.id}")]])
    await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"طلب إيداع: {amt} ج\nمن: {message.from_user.full_name}", reply_markup=kb)
    await message.answer("تم إرسال الطلب للإدارة.")
    await state.clear()

# --- إتمام الشراء وحساب التكلفة ---
@dp.callback_query(F.data.startswith("buy_"))
async def select_service(call: types.CallbackQuery, state: FSMContext):
    _, cat, sid = call.data.split("_")
    await state.update_data(sid=sid, cat=cat)
    await call.message.answer("أدخل الكمية المطلوبة:")
    await state.set_state(UserStates.waiting_for_quantity)

@dp.message(UserStates.waiting_for_quantity)
async def get_qty(msg: types.Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("يجب إدخال أرقام فقط!")
    qty = int(msg.text)
    data = await state.get_data()
    price = CATEGORIES[data['cat']]['services'][data['sid']]['price']
    total = (qty / 1000) * price
    await state.update_data(qty=qty, total=total)
    await msg.answer(f"💰 التكلفة الإجمالية: {total} ج.م\nأرسل الرابط الآن للتنفيذ:")
    await state.set_state(UserStates.waiting_for_link)

@dp.message(UserStates.waiting_for_link)
async def finish_order(msg: types.Message, state: FSMContext):
    if not re.match(r'https?://', msg.text): return await msg.answer("رابط غير صحيح!")
    data = await state.get_data()
    payload = {'key': API_KEY, 'action': 'add', 'service': data['sid'], 'link': msg.text, 'quantity': data['qty']}
    req = requests.post(SMMWIZ_URL, data=payload)
    if req.status_code == 200:
        order_id = req.json().get('order')
        cursor.execute("INSERT INTO orders VALUES (?, ?, 'Pending')", (order_id, msg.from_user.id))
        db.commit()
        await msg.answer("✅ تم إرسال طلبك! سأقوم بإخطارك بتحديثات التنفيذ.")
    else: await msg.answer("❌ خطأ في الاتصال بالخدمة.")
    await state.clear()

# --- دوال الربط ---
@dp.callback_query(F.data == "main_menu")
async def back_to_main(call: types.CallbackQuery):
    await call.message.edit_text("أهلاً بك في Tik Wolf! 🐺 اختر من القائمة:", reply_markup=main_menu())

@dp.callback_query(F.data.startswith("app_"))
async def approve(call: types.CallbackQuery):
    _, uid, amt = call.data.split("_")
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amt, uid))
    db.commit()
    await call.message.edit_caption(caption="✅ تمت الموافقة.")
    await bot.send_message(uid, f"🎉 تم إضافة {amt} جنيه لرصيدك!")

async def main():
    asyncio.create_task(check_order_status()) # تشغيل المراقبة التلقائية
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
