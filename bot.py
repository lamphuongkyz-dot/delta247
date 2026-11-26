
import requests
import io
import subprocess
import telebot
from flask import Flask, request, abort
import json
import os
import uuid
import urllib.parse
from dotenv import load_dotenv
from supabase import create_client
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

print("KET NOI SUPABASE THANH CONG")
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 5339577127

BANK = "VCB"
ACCOUNT = "1029586739"
OWNER = "NGUYEN LAM PHUONG"

if not TOKEN:
    raise RuntimeError("Chưa cấu hình BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)
def setup_commands():
    commands = [
telebot.types.BotCommand("addproduct", "Thêm sản phẩm"),
telebot.types.BotCommand("editproduct", "Sửa sản phẩm"),
telebot.types.BotCommand("delproduct", "Xóa sản phẩm"),
telebot.types.BotCommand("products", "Danh sách sản phẩm"),
        telebot.types.BotCommand("admin", "Bảng quản trị"),
        telebot.types.BotCommand("stock", "Kiểm tra kho key"),
        telebot.types.BotCommand("addkey", "Thêm key mới"),
        telebot.types.BotCommand("listkey", "Xem danh sách key"),
        telebot.types.BotCommand("delkey", "Xóa key"),
        telebot.types.BotCommand("start", "Bắt đầu mua key")
    ]

    bot.set_my_commands(
        commands,
        scope=telebot.types.BotCommandScopeChat(
            chat_id=ADMIN_ID
        )
    )






def load(file):
    if not os.path.exists(file):
        return {}
    with open(file, "r", encoding="utf-8") as f:
        return json.load(f)


def save(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
def sync_products():
    rows = supabase.table("products").select("*").execute().data
    return {
        p["product_id"]: {
            "name": p["name"],
            "price": p["price"]
        }
        for p in rows
    }

PRODUCTS = sync_products()
def is_admin(user_id):
    return user_id == ADMIN_ID


def admin_only(m):
    if not is_admin(m.from_user.id):
        bot.reply_to(m, "⛔ Mày không có quyền sử dụng lệnh này.")
        return False
    return True


# ================= ADMIN =================

import shlex
import re

@bot.message_handler(commands=["addproduct"])
def add_product(m):
    if not admin_only(m):
        return

    try:
        parts = shlex.split(m.text)
        if len(parts) != 4:
            raise ValueError

        pid, name, price = parts[1], parts[2], int(parts[3])

        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,20}", pid):
            bot.reply_to(m, "ID chỉ được chứa chữ, số, _ hoặc -")
            return

        if pid in PRODUCTS:
            bot.reply_to(m, "Sản phẩm đã tồn tại.")
            return

        if not name.strip() or price <= 0:
            bot.reply_to(m, "Tên hoặc giá không hợp lệ.")
            return

        supabase.table("products").insert({
            "product_id": pid,
            "name": name,
            "price": price
        }).execute()

        PRODUCTS[pid] = {
            "name": name,
            "price": price
        }
        bot.reply_to(
            m,
            f"✅ Đã tạo sản phẩm!\n"
            f"ID: {pid}\nTên: {name}\nGiá: {price:,}đ"
        )

    except (ValueError, IndexError):
        bot.reply_to(
            m,
            'Cách dùng:\n/addproduct 1w "Key 1 tuần" 350000'
        )


@bot.message_handler(commands=["editproduct"])
def edit_product(m):
    if not admin_only(m):
        return

    try:
        parts = shlex.split(m.text)

        if len(parts) != 4:
            raise ValueError

        pid, name, price = parts[1], parts[2], int(parts[3])

        if pid not in PRODUCTS:
            bot.reply_to(m, "Không tìm thấy sản phẩm.")
            return

        if not name.strip() or price <= 0:
            bot.reply_to(m, "Tên hoặc giá không hợp lệ.")
            return




        supabase.table("products").update({
            "name": name,
            "price": price
        }).eq("product_id", pid).execute()

        PRODUCTS[pid] = {
            "name": name,
            "price": price
        }
        bot.reply_to( m, f"✅ Đã cập nhật!\n" 
            f"{name}\nGiá mới: {price:,}đ"

        )

    except (ValueError, IndexError):
        bot.reply_to(
            m,
            'Cách dùng:\n/editproduct 1w "Key 1 tuần" 370000'
        )


@bot.message_handler(commands=["delproduct"])
def delete_product(m):
    if not admin_only(m):
        return

    parts = m.text.split()

    if len(parts) != 2:
        bot.reply_to(m, "Cách dùng: /delproduct 1w")
        return

    pid = parts[1]

    if pid not in PRODUCTS:
        bot.reply_to(m, "Không tìm thấy sản phẩm.")
        return
    keys = supabase.table("keys").select("id").eq(
        "product_id", pid
    ).execute().data

    if keys:
        bot.reply_to(
            m,
            "⚠️ Sản phẩm vẫn còn key trong kho. "
            "Hãy xử lý kho trước khi xóa."
        )
        return

    orders = load("orders.json")
    pending = any(
        o.get("product") == pid and o.get("status") == "pending"
        for o in orders.values()
    )

    if pending:
        bot.reply_to(m, "⚠️ Sản phẩm còn đơn chưa xử lý.")
        return



    supabase.table("products").delete().eq(
        "product_id", pid
    ).execute()

    del PRODUCTS[pid]
    bot.reply_to(m, f"🗑 Đã xóa sản phẩm {pid}.")


@bot.message_handler(commands=["products"])
def show_products(m):
    if not admin_only(m):
        return

    if not PRODUCTS:
        bot.reply_to(m, "Chưa có sản phẩm.")
        return

    msg = "🛍 DANH SÁCH SẢN PHẨM\n\n"

    for pid, p in PRODUCTS.items():
        msg += (
            f"ID: {pid}\n"
            f"Tên: {p['name']}\n"
            f"Giá: {p['price']:,}đ\n\n"
        )

    bot.reply_to(m, msg)

@bot.message_handler(commands=["admin"])
def admin(m):
    if not admin_only(m):
        return

    bot.reply_to(
        m,
        "🔥 DELTA247 ADMIN\n\n"
        "/stock - Xem kho key\n"
        "/addkey 6h KEY - Thêm key 6 giờ\n"
        "/addkey 1d KEY - Thêm key 1 ngày\n"
        "/listkey 6h - Danh sách key\n"
        "/delkey 6h 1 - Xóa key theo số thứ tự\n"
"/addproduct 1w \"Key 1 tuần\" 350000 - Thêm sản phẩm\n"
"/editproduct 1w \"Key 1 tuần\" 370000 - Sửa sản phẩm\n"
"/delproduct 1w - Xóa sản phẩm\n"
"/products - Xem danh sách sản phẩm\n"
    )


@bot.message_handler(commands=["addkey"])
def add_key(m):
    if not admin_only(m):
        return

    parts = m.text.split(maxsplit=2)

    if len(parts) != 3:
        bot.reply_to(m, "Cách dùng:\n/addkey 6h KEY_CUA_MAY")
        return

    pid, key = parts[1], parts[2].strip()

    if pid not in PRODUCTS:
        bot.reply_to(m, "❌ Loại key không tồn tại.")
        return

    if not key:
        bot.reply_to(m, "❌ Key không được để trống.")
        return

    existing = supabase.table("keys").select("key_value").eq(
        "product_id", pid
    ).execute().data

    if any(k["key_value"] == key for k in existing):
        bot.reply_to(m, "⚠️ Key này đã có trong kho.")
        return

    supabase.table("keys").insert({
        "product_id": pid,
        "key_value": key
    }).execute()

    total = len(existing) + 1


    bot.reply_to(
        m,
        f"✅ Đã thêm key thành công!\n"
        f"Loại: {PRODUCTS[pid]['name']}\n"
        f"Key: {key}\n"
f"Tồn kho: {total}"
    )


@bot.message_handler(commands=["stock"])
def stock(m):
    if not admin_only(m):
        return

    msg = "📦 KHO KEY DELTA247\n\n"

    for pid, p in PRODUCTS.items():
        count = len(
            supabase.table("keys").select("id").eq(
                "product_id", pid
            ).execute().data
        )
        msg += f"{p['name']}: {count} key\n"

    bot.reply_to(m, msg)

    bot.reply_to(m, msg)


@bot.message_handler(commands=["listkey"])
def list_key(m):
    if not admin_only(m):
        return

    parts = m.text.split()

    if len(parts) != 2 or parts[1] not in PRODUCTS:
        bot.reply_to(m, "Cách dùng: /listkey 6h")
        return

    pid = parts[1]
    items = supabase.table("keys").select("*").eq(
        "product_id", pid
    ).order("id").execute().data

    items = [k["key_value"] for k in items]

    if not items:
        bot.reply_to(m, "📭 Kho key đang trống.")
        return
    msg = f"📦 DANH SÁCH {PRODUCTS[pid]['name']}\n\n"

    for i, key in enumerate(items, 1):
        msg += f"{i}. {key}\n"

    bot.reply_to(m, msg)


@bot.message_handler(commands=["delkey"])
def delete_key(m):
    if not admin_only(m):
        return

    parts = m.text.split()

    if len(parts) != 3:
        bot.reply_to(m, "Cách dùng: /delkey 6h 1")
        return

    pid = parts[1]

    if pid not in PRODUCTS:
        bot.reply_to(m, "❌ Loại key không tồn tại.")
        return

    try:
        index = int(parts[2]) - 1
    except ValueError:
        bot.reply_to(m, "❌ Số thứ tự không hợp lệ.")
        return

    items = supabase.table("keys").select("*").eq(
        "product_id", pid
    ).order("id").execute().data

    if index < 0 or index >= len(items):
        bot.reply_to(m, "❌ Không tìm thấy key ở vị trí đó.")
        return

    removed = items[index]

    supabase.table("keys").delete().eq(
        "id", removed["id"]
    ).execute()

    bot.reply_to(m, f"🗑 Đã xóa key:\n{removed['key_value']}")



# ================= KHÁCH HÀNG =================

@bot.message_handler(commands=["start"])
def start(m):
    kb = telebot.types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        row_width=2
    )

    kb.add(
        "🛒 Mua key",
        "📦 Đơn hàng"
    )
    kb.add(
        "👤 Tài khoản",
        "💬 Hỗ trợ"
    )

    bot.send_message(
        m.chat.id,
        "⚡ DELTA247 SHOP ⚡\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🔥 CHÀO MỪNG ĐẾN VỚI DELTA247\n\n"
        "🛍️ Shop cung cấp các gói KEY\n"
        "⚡ Giao key tự động sau thanh toán\n"
        "💳 Thanh toán bằng chuyển khoản ngân hàng\n"
        "🔒 Hệ thống xử lý đơn hàng tự động\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "👇 CHỌN CHỨC NĂNG BÊN DƯỚI",
        reply_markup=kb
    )


@bot.message_handler(func=lambda m: m.text == "🛒 Mua key")
def buy(m):
    kb = telebot.types.InlineKeyboardMarkup()

    for pid, p in PRODUCTS.items():
        kb.add(
            telebot.types.InlineKeyboardButton(
                f"{p['name']} - {p['price']:,}đ",
                callback_data=f"buy_{pid}"
            )
        )

    bot.send_message(
        m.chat.id,
        "Chọn loại key:",
        reply_markup=kb
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_"))
def choose(c):
    pid = c.data[4:]

    if pid not in PRODUCTS:
        bot.answer_callback_query(c.id, "Sản phẩm không tồn tại")
        return

    p = PRODUCTS[pid]
    order_id = uuid.uuid4().hex[:8].upper()

    orders = load("orders.json")

    orders[order_id] = {
        "user_id": c.from_user.id,
        "product": pid,
        "status": "pending"
    }

    save("orders.json", orders)

    qr = (
        f"https://img.vietqr.io/image/{BANK}-{ACCOUNT}-compact2.png"
        f"?amount={p['price']}"
        f"&addInfo={urllib.parse.quote('DELTA' + order_id)}"
        f"&accountName={urllib.parse.quote(OWNER)}"
    )

    kb = telebot.types.InlineKeyboardMarkup()

    kb.add(
        telebot.types.InlineKeyboardButton(
            "📨 Báo đã chuyển khoản",
            callback_data=f"paid_{order_id}"
        )
    )

    try:
        r = requests.get(qr, timeout=30)
        r.raise_for_status()

        if "svg" in r.headers.get("Content-Type", "").lower():
            converted = subprocess.run(
                ["rsvg-convert", "-f", "png"],
                input=r.content,
                capture_output=True,
                check=True
            )
            image_data = converted.stdout
        else:
            image_data = r.content

        qr_file = io.BytesIO(image_data)
        qr_file.name = "qr.png"

        bot.send_photo(
            c.message.chat.id,
            qr_file,
            caption=(
                f"🔥 ĐƠN HÀNG {order_id}\n"
                f"Sản phẩm: {p['name']}\n"
                f"Số tiền: {p['price']:,}đ\n"
                f"Ngân hàng: Vietcombank\n"
                f"STK: {ACCOUNT}\n"
                f"Chủ TK: {OWNER}\n"
                f"Nội dung CK: DELTA{order_id}\n\n"
                "Chuyển khoản đúng số tiền và nội dung nhé."
            ),
            reply_markup=kb
        )

    except Exception as e:
        print("LỖI GỬI QR:", repr(e))

        bot.send_message(
            c.message.chat.id,
            f"Đơn hàng {order_id} đã tạo.\n"
            f"Số tiền: {p['price']:,}đ\n"
            f"STK: {ACCOUNT}\n"
            f"Chủ TK: {OWNER}\n"
            f"Nội dung CK: DELTA{order_id}",
            reply_markup=kb
        )

    bot.answer_callback_query(c.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("paid_"))
def paid(c):
    oid = c.data[5:]
    orders = load("orders.json")

    if oid not in orders or orders[oid]["user_id"] != c.from_user.id:
        bot.answer_callback_query(c.id, "Đơn không hợp lệ")
        return

    if orders[oid]["status"] != "pending":
        bot.answer_callback_query(c.id, "Đơn đã được xử lý")
        return

    bot.send_message(
        c.message.chat.id,
        "Đã báo chuyển khoản. Vui lòng chờ admin kiểm tra."
    )

    kb = telebot.types.InlineKeyboardMarkup()

    kb.add(
        telebot.types.InlineKeyboardButton(
            "✅ Xác nhận đã nhận tiền",
            callback_data=f"confirm_{oid}"
        )
    )

    bot.send_message(
        ADMIN_ID,
        f"Đơn {oid}\n"
        f"Khách: {c.from_user.id}\n"
        f"Sản phẩm: {orders[oid]['product']}",
        reply_markup=kb
    )

    bot.answer_callback_query(c.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("confirm_"))
def confirm_order(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id, "Không có quyền")
        return

    oid = c.data.replace("confirm_", "")
    orders = load("orders.json")


    if oid not in orders:
        bot.answer_callback_query(c.id, "Không tìm thấy đơn")
        return

    order = orders[oid]

    if order["status"] != "pending":
        bot.answer_callback_query(c.id, "Đơn đã xử lý")
        return

    pid = order["product"]

    available = supabase.table("keys").select(
        "id", "key_value"
    ).eq("product_id", pid).order("id").limit(1).execute().data

    if not available:
        bot.answer_callback_query(c.id, "Kho key đã hết")
        return

    key_row = available[0]
    key = key_row["key_value"]

    supabase.table("keys").delete().eq(
        "id", key_row["id"]
    ).execute()
    order["status"] = "completed"
    save("orders.json", orders)

    try:
        bot.send_message(
            order["user_id"],
            f"🎉 THANH TOÁN THÀNH CÔNG!\n\n"
            f"Key của bạn:\n`{key}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        print("LỖI GỬI KEY:", repr(e))

    bot.answer_callback_query(c.id, "Đã giao key")

    bot.send_message(
        ADMIN_ID,
        f"✅ Đã giao đơn {oid} thành công.\n"
        f"Kho còn: {len(keys[pid])} key."
    )

# ================= ĐƠN HÀNG =================

@bot.message_handler(func=lambda m: m.text == "📦 Đơn hàng")
def my_orders(m):
    orders = load("orders.json")
    user_orders = [
        (oid, o) for oid, o in orders.items()
        if o.get("user_id") == m.from_user.id
    ]

    if not user_orders:
        bot.send_message(m.chat.id, "📦 Bạn chưa có đơn hàng nào.")
        return

    status_text = {
        "pending": "⏳ Chờ thanh toán",
        "completed": "✅ Đã giao key"
    }

    msg = "📦 LỊCH SỬ ĐƠN HÀNG\n━━━━━━━━━━━━━━━━━━\n"

    for oid, order in sorted(user_orders, reverse=True):
        pid = order.get("product")
        p = PRODUCTS.get(pid, {})
        name = p.get("name", pid)
        price = p.get("price", order.get("amount", 0))
        status = status_text.get(
            order.get("status"), order.get("status", "Không rõ")
        )

        msg += (
            f"\n🧾 Mã đơn: {oid}\n"
            f"📦 Sản phẩm: {name}\n"
            f"💰 Giá: {price:,}đ\n"
            f"📌 Trạng thái: {status}\n"
            "━━━━━━━━━━━━━━━━━━\n"
        )

    bot.send_message(m.chat.id, msg)


# ================= TÀI KHOẢN =================

@bot.message_handler(func=lambda m: m.text == "👤 Tài khoản")
def my_account(m):
    orders = load("orders.json")

    user_orders = [
        o for o in orders.values()
        if o.get("user_id") == m.from_user.id
    ]

    total = sum(
        PRODUCTS.get(o.get("product"), {}).get(
            "price", o.get("amount", 0)
        )
        for o in user_orders
        if o.get("status") == "completed"
    )

    completed = sum(
        1 for o in user_orders
        if o.get("status") == "completed"
    )

    bot.send_message(
        m.chat.id,
        "👤 THÔNG TIN TÀI KHOẢN\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🆔 Telegram ID: {m.from_user.id}\n"
        f"👤 Tên: {m.from_user.first_name}\n"
        f"📦 Tổng đơn: {len(user_orders)}\n"
        f"✅ Đơn hoàn thành: {completed}\n"
        f"💰 Tổng tiền đã mua: {total:,}đ\n"
        "━━━━━━━━━━━━━━━━━━"
    )


@bot.message_handler(func=lambda m: m.text == "💬 Hỗ trợ")
def support(m):
    kb = telebot.types.InlineKeyboardMarkup()
    kb.add(
        telebot.types.InlineKeyboardButton(
            "📲 NHẮN TIN ZALO",
            url="https://zalo.me/0395929084"
        )
    )

    bot.send_message(
        m.chat.id,
        "💬 HỖ TRỢ KHÁCH HÀNG DELTA247\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "📱 Zalo: 0395929084\n\n"
        "Nhấn nút bên dưới để liên hệ shop nhé!",
        reply_markup=kb
    )

app = Flask(__name__)

@app.route("/")
def home():
    return "DELTA247 BOT ONLINE", 200

@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    secret = os.getenv("WEBHOOK_SECRET")

    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret:
        abort(403)

    json_data = request.get_json(silent=True)
    if json_data:
        update = telebot.types.Update.de_json(json_data)
        bot.process_new_updates([update])

    return "OK", 200


print("DELTA247 WEBHOOK DANG KHOI DONG...")
setup_commands()

render_url = os.getenv("RENDER_EXTERNAL_URL")
webhook_secret = os.getenv("WEBHOOK_SECRET")

if not render_url or not webhook_secret:
    raise RuntimeError("Thieu RENDER_EXTERNAL_URL hoac WEBHOOK_SECRET")

bot.set_webhook(
    url=f"{render_url}/telegram",
    secret_token=webhook_secret
)

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 10000))
    )
