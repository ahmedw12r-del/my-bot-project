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
BOT_TOKEN = "8960056224:AAGMIz19XsxzA7u81NGu8X6tgSL3awwlMSE"
API_KEY = "758ce41e3232ffe511f240c4d184fdb4"
ADMIN_ID = 8201315070
SMMWIZ_URL = "https://smmwiz.com/api/v2"
WHATSAPP_LINK = "https://wa.me/201011496150"

logging.basicConfig(level=logging.INFO)

# --- الخدمات (يمكنك إضافة المزيد هنا) ---
CATEGORIES = {
    "insta": {"name": "📸 Instagram", "services": {"17678": {"name": "Followers", "price": 35}, "20216": {"name": "Likes", "price": 20}, "14245": {"name": "Views", "price": 6}}},
    "fb": {"name": "🔵 Facebook", "services": {"17333": {"name": "Followers", "price": 35}, "2981": {"name": "Likes", "price": 20}}},
    "tiktok": {"name": "🎵 TikTok", "services": {"11775": {"name": "Likes", "price": 20}, "19967": {"name": "Views", "price": 6}}}
}

# --- تهيئة البوت وقاعدة البيانات ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
db = sqlite3.connect("store.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, balance REAL DEFAULT 0)")
cursor.execute("CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, user_id INTEGER, status TEXT)")
db.commit()

class UserStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_amount = State()
    waiting_for_photo = State()
    waiting_for_quantity = State()
    waiting_for_link = State()

# --- دالة مراقبة الطلبات ---
async def check_order_status():
    while True:
        cursor.execute("SELECT order_id, user_id FROM orders WHERE status != 'Completed'")
        for o_id, u_id in cursor.fetchall():
            try:
                res = requests.post(SMMWIZ_URL, data={'key': API_KEY, 'action': 'status', 'order': o_id}).json()
                if res.get('status') == 'Completed':
                    cursor.execute("UPDATE orders SET status = 'Completed' WHERE order_id = ?", (o_id,))
                    db.commit()
                    await bot.send_message(u_id, "✅ **تهانينا!** تم تنفيذ طلبك بنجاح.")
            except: pass
        await asyncio.sleep(120)

# --- الواجهات ---
def main_menu():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🛒 ── تصفح وشراء الخدمات ── 🛒", callback_data="categories")],
        [types.InlineKeyboardButton(text="💰 ── شحن الرصيد (InstaPay/VF Cash) ── 💰", callback_data="add_balance")],
        [types.InlineKeyboardButton(text="💳 ── لوحة التحكم الشخصية ── 💳", callback_data="check_balance")],
        [types.InlineKeyboardButton(text="🎧 ── الدعم الفني ── 🎧", url=WHATSAPP_LINK)]
    ])

# --- الأوامر الأساسية ---
@dp.message(Command("start"))
async def start(message: types.Message, state: FSMContext):
    cursor.execute("SELECT name FROM users WHERE user_id=?", (message.from_user.id,))
    if not cursor.fetchone():
        await message.answer("🐺 أهلاً بك في Tik Wolf! يرجى كتابة اسمك للبدء:")
        await state.set_state(UserStates.waiting_for_name)
    else:
        await message.answer("🏠 أهلاً بك مجدداً في Tik Wolf، اختر الخدمة:", reply_markup=main_menu())

@dp.message(UserStates.waiting_for_name)
async def set_name(message: types.Message, state: FSMContext):
    cursor.execute("INSERT INTO users (user_id, name, balance) VALUES (?, ?, 0)", (message.from_user.id, message.text))
    db.commit()
    await message.answer("تم حفظ بياناتك بنجاح! ✅", reply_markup=main_menu())
    await state.clear()

# --- نظام الشحن ---
@dp.callback_query(F.data == "add_balance")
async def add_balance(call: types.CallbackQuery, state: FSMContext):
    text = ("💰 **نظام شحن الرصيد** 💰\n\n"
            "مرحباً بك، للشحن يرجى التحويل عبر:\n"
            "🔹 **فودافون كاش:** `01011496150`\n"
            "🔹 **InstaPay:** عنوانك البريدي أو رقم الهاتف المحول له.\n\n"
            "الرجاء إرسال المبلغ (أرقام فقط) ثم سكرين شوت للتحويل.")
    await call.message.edit_text(text, parse_mode="Markdown", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="🔙 عودة", callback_data="main_menu")]]))
    await state.set_state(UserStates.waiting_for_amount)

@dp.message(UserStates.waiting_for_amount)
async def get_amount(message: types.Message, state: FSMContext):
    await state.update_data(amount=message.text)
    await message.answer("✅ تم تحديد المبلغ! الآن أرسل صورة (سكرين شوت) التحويل:")
    await state.set_state(UserStates.waiting_for_photo)

@dp.message(UserStates.waiting_for_photo, F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    amt = data.get('amount')
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ قبول الإيداع", callback_data=f"app_{message.from_user.id}_{amt}")],
        [types.InlineKeyboardButton(text="❌ رفض", callback_data=f"rej_{message.from_user.id}")]
    ])
    await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"💸 طلب شحن!\nالمبلغ: {amt} ج.م\nالعميل: {message.from_user.full_name}", reply_markup=kb)
    await message.answer("✅ تم إرسال طلبك للإدارة للمراجعة.")
    await state.clear()

# --- لوحة التحكم ---
@dp.callback_query(F.data == "check_balance")
async def show_dashboard(call: types.CallbackQuery):
    cursor.execute("SELECT name, balance FROM users WHERE user_id=?", (call.from_user.id,))
    user = cursor.fetchone()
    name, bal = user if user else ("غير مسجل", 0)
    msg = (f"📊 **لوحة التحكم الشخصية**\n\n"
           f"👤 الاسم: {name}\n"
           f"💰 رصيدك المتاح: {bal} ج.م\n"
           f"🆔 ID: `{call.from_user.id}`")
    await call.message.edit_text(msg, parse_mode="Markdown", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="🔙 عودة", callback_data="main_menu")]]))

# --- دوال الخدمات ---
@dp.callback_query(F.data == "categories")
async def show_cats(call: types.CallbackQuery):
    btns = [[types.InlineKeyboardButton(text=v['name'], callback_data=f"cat_{k}")] for k, v in CATEGORIES.items()]
    btns.append([types.InlineKeyboardButton(text="🔙 عودة", callback_data="main_menu")])
    await call.message.edit_text("اختر المنصة:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("cat_"))
async def show_services(call: types.CallbackQuery):
    cat = call.data.split("_")[1]
    btns = [[types.InlineKeyboardButton(text=f"{v['name']} ({v['price']} ج/1000)", callback_data=f"buy_{cat}_{sid}")] for sid, v in CATEGORIES[cat]['services'].items()]
    await call.message.edit_text("اختر الخدمة:", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("buy_"))
async def select_service(call: types.CallbackQuery, state: FSMContext):
    _, cat, sid = call.data.split("_")
    await state.update_data(sid=sid, cat=cat)
    await call.message.answer("📝 أدخل الكمية:")
    await state.set_state(UserStates.waiting_for_quantity)

@dp.message(UserStates.waiting_for_quantity)
async def get_qty(msg: types.Message, state: FSMContext):
    await state.update_data(qty=int(msg.text))
    await msg.answer("🔗 أرسل الرابط الآن:")
    await state.set_state(UserStates.waiting_for_link)

@dp.message(UserStates.waiting_for_link)
async def finish_order(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    # عملية الشراء من الموقع
    req = requests.post(SMMWIZ_URL, data={'key': API_KEY, 'action': 'add', 'service': data['sid'], 'link': msg.text, 'quantity': data['qty']}).json()
    if 'order' in req:
        cursor.execute("INSERT INTO orders VALUES (?, ?, 'Pending')", (req['order'], msg.from_user.id))
        db.commit()
        await msg.answer("✅ تم طلب الخدمة بنجاح!")
    await state.clear()

# --- الإدارة ---
@dp.callback_query(F.data.startswith("app_"))
async def approve(call: types.CallbackQuery):
    _, uid, amt = call.data.split("_")
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amt, uid))
    db.commit()
    await call.message.edit_caption(caption="✅ تمت الموافقة.")
    await bot.send_message(uid, f"🎉 تم شحن رصيدك بـ {amt} ج.م")

# --- تشغيل البوت ---
async def main():
    asyncio.create_task(check_order_status())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
