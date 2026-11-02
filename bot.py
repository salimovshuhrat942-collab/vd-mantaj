"""
Video montaj buyurtma boti
aiogram 3 + SQLite  |  Railway uchun tayyor

Oqim:
  /start -> ma'lumot + [Keyingisi] -> to'lov (karta) -> chek rasmi -> videolar
  -> kanalga tushadi (Tasdiqlash / Rad etish) -> admin tayyor videoni bot orqali yuboradi
"""
import asyncio
import html
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone

import aiosqlite
from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.filters import BaseFilter, Command, invert_f
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    CallbackQuery,
    ErrorEvent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyParameters,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
log = logging.getLogger("montaj")

# ----------------------------------------------------------------------------
# SOZLAMALAR (Railway Variables orqali)
# ----------------------------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {
    int(x)
    for x in re.split(r"[,\s;]+", os.getenv("ADMIN_IDS") or os.getenv("ADMIN_ID") or "")
    if x.lstrip("-").isdigit()
}
CHANNEL_ID = int((os.getenv("CHANNEL_ID") or "0").strip() or 0)
DATA_DIR = os.getenv("DATA_DIR", "./data")
TZ = timezone(timedelta(hours=5))  # Toshkent

bot = Bot(BOT_TOKEN or "0:invalid", default=DefaultBotProperties(parse_mode=ParseMode.HTML))
r = Router()
DB: aiosqlite.Connection = None  # type: ignore
BOT_ID = 0

# ----------------------------------------------------------------------------
# STANDART MATNLAR (admin paneldan o'zgartiriladi)
# ----------------------------------------------------------------------------
DEFAULTS = {
    "price": "50000",
    "card": "",
    "holder": "",
    "orders_open": "1",
    "welcome_photo": "",
    "pay_photo": "",
    "btn_next": "Keyingisi ➡️",
    "welcome_text": (
        "🎬 <b>Professional video montaj xizmati</b>\n\n"
        "Assalomu alaykum! Bu bot orqali videolaringizni sifatli montaj qildirishingiz mumkin.\n\n"
        "✨ <b>Nimalar qilamiz:</b>\n"
        "• Videoni kesish va birlashtirish\n"
        "• Effekt, o'tish (transition), rang tuzatish\n"
        "• Musiqa, subtitr va yozuvlar qo'shish\n"
        "• Reels / TikTok / YouTube formatiga moslash\n\n"
        "💰 Narxi: <b>{price} so'm</b>\n\n"
        "⚡️ <b>Qanday ishlaydi?</b>\n"
        "1️⃣ To'lovni amalga oshirasiz\n"
        "2️⃣ To'lov chekini yuborasiz\n"
        "3️⃣ Montaj qilinadigan videolarni yuborasiz\n"
        "4️⃣ Tayyor videoni shu bot orqali olasiz\n\n"
        "Boshlash uchun pastdagi tugmani bosing 👇"
    ),
    "pay_text": (
        "💳 <b>To'lov</b>\n\n"
        "Montaj narxi: <b>{price} so'm</b>\n\n"
        "Karta raqami:\n<code>{card}</code>\n"
        "Karta egasi: <b>{holder}</b>\n\n"
        "1️⃣ Yuqoridagi kartaga to'lovni amalga oshiring\n"
        "2️⃣ To'lov <b>chekini (skrinshot)</b> rasm qilib shu yerga yuboring 📸"
    ),
    "videos_text": (
        "✅ <b>Chek qabul qilindi!</b>\n\n"
        "Endi montaj qilinishi kerak bo'lgan <b>videolaringizni</b> yuboring 🎬\n"
        "Bir nechta video yuborishingiz mumkin. Hammasini yuborib bo'lgach, "
        "«✅ Yuborib bo'ldim» tugmasi chiqadi."
    ),
    "submitted_text": (
        "🎉 <b>Buyurtmangiz #{id} qabul qilindi!</b>\n\n"
        "To'lovingiz tekshirilmoqda. Tasdiqlangach sizga xabar beramiz, "
        "tayyor video shu yerga yuboriladi."
    ),
    "accepted_text": (
        "✅ <b>To'lovingiz tasdiqlandi!</b>\n\n"
        "Buyurtma #{id} bo'yicha montaj boshlandi. Tayyor bo'lgach video shu bot orqali yuboriladi ⏳"
    ),
    "reject_text": (
        "❌ <b>Buyurtma #{id} rad etildi.</b>\n\n"
        "To'lov amalga oshirilmagani aniqlandi. Agar adashgan bo'lsangiz, "
        "to'lovni qilib, qaytadan urinib ko'ring."
    ),
    "done_text": "🎉 Buyurtma #{id} — montajingiz tayyor!\nRahmat, yana kutib qolamiz 🤝",
    "closed_text": "⏸ Hozircha buyurtmalar qabul qilinmayapti. Keyinroq urinib ko'ring.",
}

TEXT_KEYS = [
    ("welcome_text", "👋 Boshlang'ich matn"),
    ("pay_text", "💳 To'lov matni"),
    ("videos_text", "🎬 Video so'rash matni"),
    ("submitted_text", "📨 Buyurtma qabul qilindi"),
    ("accepted_text", "✅ To'lov tasdiqlandi"),
    ("reject_text", "❌ Rad etish matni"),
    ("done_text", "🎉 Tayyor video izohi"),
    ("closed_text", "⏸ Buyurtma yopiq matni"),
    ("btn_next", "🔘 «Keyingisi» tugma nomi"),
]
PHOTO_KEYS = [
    ("welcome_photo", "🖼 Boshlang'ich rasm"),
    ("pay_photo", "🖼 To'lov sahifasi rasmi"),
]

STATUS = {
    "receipt": "🧾 Chek kutilmoqda",
    "videos": "🎬 Video kutilmoqda",
    "pending": "⏳ Kutilmoqda",
    "approved": "✅ Tasdiqlangan (montajda)",
    "rejected": "❌ Rad etilgan",
    "done": "📦 Yakunlangan",
    "cancelled": "🚫 Bekor qilingan",
}
EMO = {k: v.split()[0] for k, v in STATUS.items()}

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY, username TEXT, full_name TEXT,
    joined_at INTEGER, last_seen INTEGER, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS orders(
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, status TEXT, price INTEGER,
    receipt_id TEXT, receipt_kind TEXT, video_count INTEGER DEFAULT 0,
    prompt_msg_id INTEGER, card_msg_id INTEGER,
    created_at INTEGER, submitted_at INTEGER, decided_at INTEGER, decided_by INTEGER);
CREATE TABLE IF NOT EXISTS order_videos(
    id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER, user_msg_id INTEGER, ch_msg_id INTEGER);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS channels(
    id INTEGER PRIMARY KEY, title TEXT, link TEXT, added_at INTEGER);
CREATE TABLE IF NOT EXISTS states(user_id INTEGER PRIMARY KEY, action TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS promos(
    code TEXT PRIMARY KEY, percent INTEGER, active INTEGER DEFAULT 1,
    used INTEGER DEFAULT 0, created_at INTEGER);
"""


# ----------------------------------------------------------------------------
# DB yordamchilar
# ----------------------------------------------------------------------------
async def fetch(sql, *a):
    cur = await DB.execute(sql, a)
    rows = await cur.fetchall()
    await cur.close()
    return rows


async def one(sql, *a):
    rows = await fetch(sql, *a)
    return rows[0] if rows else None


async def run(sql, *a):
    cur = await DB.execute(sql, a)
    await DB.commit()
    res = (cur.lastrowid, cur.rowcount)
    await cur.close()
    return res


async def gs(key):
    row = await one("SELECT value FROM settings WHERE key=?", key)
    return row["value"] if row else DEFAULTS.get(key, "")


async def ss(key, val):
    await run(
        "INSERT INTO settings(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        key,
        val,
    )


async def set_state(uid, action, data=None):
    await run(
        "INSERT OR REPLACE INTO states(user_id,action,data) VALUES(?,?,?)",
        uid,
        action,
        json.dumps(data or {}),
    )


async def get_state(uid):
    row = await one("SELECT action,data FROM states WHERE user_id=?", uid)
    if not row:
        return None
    return row["action"], json.loads(row["data"] or "{}")


async def clear_state(uid):
    await run("DELETE FROM states WHERE user_id=?", uid)


async def touch_user(u):
    now = int(time.time())
    await run(
        "INSERT INTO users(id,username,full_name,joined_at,last_seen,active) VALUES(?,?,?,?,?,1) "
        "ON CONFLICT(id) DO UPDATE SET username=excluded.username, full_name=excluded.full_name, "
        "last_seen=excluded.last_seen, active=1",
        u.id,
        u.username,
        u.full_name,
        now,
        now,
    )


# ----------------------------------------------------------------------------
# Umumiy yordamchilar
# ----------------------------------------------------------------------------
def fmt(n):
    try:
        return f"{int(n):,}".replace(",", " ")
    except (TypeError, ValueError):
        return str(n)


def fdt(ts):
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts, TZ).strftime("%d.%m.%Y %H:%M")


def kb(*rows):
    """kb([("Matn","data")], [("Link","https://...")])"""
    out = []
    for row in rows:
        line = []
        for t, d in row:
            if d.startswith("http"):
                line.append(InlineKeyboardButton(text=t, url=d))
            else:
                line.append(InlineKeyboardButton(text=t, callback_data=d))
        out.append(line)
    return InlineKeyboardMarkup(inline_keyboard=out)


async def render(key, oid=None):
    s = await gs(key)
    card = await gs("card")
    holder = await gs("holder")
    price = await gs("price") or 0
    if oid:
        orow = await one("SELECT price FROM orders WHERE id=?", oid)
        if orow and orow["price"]:
            price = orow["price"]
    rep = {
        "{price}": fmt(price),
        "{card}": html.escape(card) if card else "kiritilmagan",
        "{holder}": html.escape(holder) if holder else "—",
        "{id}": str(oid or ""),
    }
    for k, v in rep.items():
        s = s.replace(k, v)
    return s


def fill(s):
    """Admin yuborgan matnni tekshirish uchun belgilarni to'ldirish (preview)."""
    for k, v in {"{price}": "50 000", "{card}": "8600 0000 0000 0000", "{holder}": "ISM FAMILIYA", "{id}": "1"}.items():
        s = s.replace(k, v)
    return s


async def send(chat_id, text, photo=None, markup=None):
    """HTML xato bo'lsa oddiy matn sifatida yuboradi."""

    async def _go(pm):
        if photo and len(text) <= 1024:
            return await bot.send_photo(chat_id, photo, caption=text, reply_markup=markup, parse_mode=pm)
        if photo:
            await bot.send_photo(chat_id, photo)
        return await bot.send_message(chat_id, text, reply_markup=markup, parse_mode=pm)

    try:
        return await _go(ParseMode.HTML)
    except TelegramBadRequest as e:
        if "parse" in str(e).lower() or "entit" in str(e).lower():
            return await _go(None)
        raise


async def safe_send(chat_id, *a, **kw):
    """Foydalanuvchi botni bloklagan bo'lsa ham yiqilmaydi."""
    try:
        return await send(chat_id, *a, **kw)
    except TelegramForbiddenError:
        await run("UPDATE users SET active=0 WHERE id=?", chat_id)
    except Exception as e:  # noqa
        log.warning("send fail %s: %s", chat_id, e)
    return None


async def show(c: CallbackQuery, text, markup=None):
    try:
        await c.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as e:
        if "not modified" in str(e).lower():
            return
        await c.message.answer(text, reply_markup=markup)


# ----------------------------------------------------------------------------
# Majburiy obuna
# ----------------------------------------------------------------------------
async def missing_channels(uid):
    miss = []
    for ch in await fetch("SELECT * FROM channels"):
        try:
            m = await bot.get_chat_member(ch["id"], uid)
            if m.status in ("left", "kicked") or (
                m.status == "restricted" and not getattr(m, "is_member", True)
            ):
                miss.append(ch)
        except Exception as e:  # bot kanalda admin emas va h.k. — o'tkazib yuboramiz
            log.warning("sub check %s: %s", ch["id"], e)
    return miss


def sub_markup(miss):
    rows = [[(f"📢 {ch['title']}", ch["link"])] for ch in miss if ch["link"]]
    rows.append([("✅ Tekshirish", "chk")])
    return kb(*rows)


SUB_TEXT = "📢 Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling, so'ng «✅ Tekshirish» tugmasini bosing:"


class Gate(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if isinstance(event, Message):
            chat = event.chat
        elif isinstance(event, CallbackQuery) and event.message:
            chat = event.message.chat
        else:
            chat = None
        if not user or user.is_bot or chat is None or chat.type != "private":
            return await handler(event, data)
        await touch_user(user)
        if user.id in ADMIN_IDS:
            return await handler(event, data)
        if isinstance(event, CallbackQuery) and event.data == "chk":
            return await handler(event, data)
        miss = await missing_channels(user.id)
        if not miss:
            return await handler(event, data)
        if isinstance(event, CallbackQuery):
            await event.answer("Avval kanallarga obuna bo'ling", show_alert=True)
        await bot.send_message(user.id, SUB_TEXT, reply_markup=sub_markup(miss))
        return None


# ----------------------------------------------------------------------------
# Buyurtma kartasi (kanal uchun)
# ----------------------------------------------------------------------------
def card_caption(o, u):
    name = html.escape(u["full_name"] or "—")
    uname = f"@{u['username']}" if u["username"] else "—"
    s = (
        f"🆕 <b>Buyurtma #{o['id']}</b>\n\n"
        f"👤 {name}\n🔗 {uname}\n🆔 <code>{u['id']}</code>\n"
        f"💰 {fmt(o['price'])} so'm\n"
        + (f"🎟 Promokod: {html.escape(o['promo_code'])} (-{o['promo_percent']}%)\n" if o["promo_code"] else "")
        + f"🎬 Videolar: {o['video_count']} ta\n"
        f"🕒 {fdt(o['submitted_at'])}\n\n"
        f"Holat: <b>{STATUS.get(o['status'], o['status'])}</b>"
    )
    return s


def card_kb(o):
    if o["status"] == "pending":
        return kb([("✅ Tasdiqlash", f"ok:{o['id']}"), ("❌ Rad etish", f"no:{o['id']}")])
    if o["status"] == "approved":
        return kb([("📤 Tayyor videoni yuborish", f"send:{o['id']}")])
    return None


async def refresh_card(oid):
    o = await one("SELECT * FROM orders WHERE id=?", oid)
    if not o or not o["card_msg_id"] or not CHANNEL_ID:
        return
    u = await one("SELECT * FROM users WHERE id=?", o["user_id"])
    try:
        await bot.edit_message_caption(
            chat_id=CHANNEL_ID,
            message_id=o["card_msg_id"],
            caption=card_caption(o, u),
            reply_markup=card_kb(o),
        )
    except TelegramBadRequest as e:
        if "not modified" not in str(e).lower():
            log.warning("refresh_card: %s", e)


async def copy_retry(*a, **kw):
    try:
        return await bot.copy_message(*a, **kw)
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after + 1)
        return await bot.copy_message(*a, **kw)


async def submit_order(o):
    """Buyurtmani kanalga yuboradi. True/False qaytaradi."""
    _, n = await run(
        "UPDATE orders SET status='pending', submitted_at=? WHERE id=? AND status='videos'",
        int(time.time()),
        o["id"],
    )
    if not n:
        return False
    o = await one("SELECT * FROM orders WHERE id=?", o["id"])
    u = await one("SELECT * FROM users WHERE id=?", o["user_id"])
    try:
        cap, markup = card_caption(o, u), card_kb(o)
        if o["receipt_kind"] == "photo":
            msg = await bot.send_photo(CHANNEL_ID, o["receipt_id"], caption=cap, reply_markup=markup)
        else:
            msg = await bot.send_document(CHANNEL_ID, o["receipt_id"], caption=cap, reply_markup=markup)
    except Exception as e:
        log.error("kanalga yuborib bo'lmadi: %s", e)
        await run("UPDATE orders SET status='videos', submitted_at=NULL WHERE id=?", o["id"])
        for a in ADMIN_IDS:
            await safe_send(
                a,
                f"⚠️ Buyurtmani kanalga yuborib bo'lmadi.\n<code>{html.escape(str(e))}</code>\n\n"
                "CHANNEL_ID to'g'riligini va bot kanalda ADMIN ekanini tekshiring.",
            )
        return False
    await run("UPDATE orders SET card_msg_id=? WHERE id=?", msg.message_id, o["id"])
    if o["promo_code"]:
        await run("UPDATE promos SET used=used+1 WHERE code=?", o["promo_code"])
    vids = await fetch("SELECT * FROM order_videos WHERE order_id=? ORDER BY id", o["id"])
    for i, v in enumerate(vids, 1):
        try:
            try:
                c = await copy_retry(
                    CHANNEL_ID,
                    o["user_id"],
                    v["user_msg_id"],
                    caption=f"🎬 #{o['id']} — {i}/{len(vids)}",
                    reply_parameters=ReplyParameters(message_id=msg.message_id),
                )
            except TelegramBadRequest:
                c = await copy_retry(
                    CHANNEL_ID,
                    o["user_id"],
                    v["user_msg_id"],
                    reply_parameters=ReplyParameters(message_id=msg.message_id),
                )
            await run("UPDATE order_videos SET ch_msg_id=? WHERE id=?", c.message_id, v["id"])
        except Exception as e:
            log.warning("video nusxalanmadi: %s", e)
        await asyncio.sleep(0.3)
    for a in ADMIN_IDS:
        await safe_send(
            a,
            f"🆕 Yangi buyurtma <b>#{o['id']}</b> — {fmt(o['price'])} so'm, {o['video_count']} ta video.",
            markup=kb([("📋 Ko'rish", f"a:ord:{o['id']}")]),
        )
    return True


async def decide(oid, approve, admin_id):
    new = "approved" if approve else "rejected"
    _, n = await run(
        "UPDATE orders SET status=?, decided_at=?, decided_by=? WHERE id=? AND status='pending'",
        new,
        int(time.time()),
        admin_id,
        oid,
    )
    if not n:
        return False
    await refresh_card(oid)
    o = await one("SELECT * FROM orders WHERE id=?", oid)
    if approve:
        await safe_send(o["user_id"], await render("accepted_text", oid))
    else:
        await safe_send(
            o["user_id"],
            await render("reject_text", oid),
            markup=kb([("🔄 Qayta urinish", "next")]),
        )
    return True


# ----------------------------------------------------------------------------
# FOYDALANUVCHI QISMI
# ----------------------------------------------------------------------------
async def show_welcome(uid):
    text = await render("welcome_text")
    photo = await gs("welcome_photo") or None
    await send(uid, text, photo, kb([(await gs("btn_next"), "next")]))


async def draft(uid):
    return await one(
        "SELECT * FROM orders WHERE user_id=? AND status IN ('promo','promo_in','receipt','videos') ORDER BY id DESC LIMIT 1",
        uid,
    )


@r.message(Command("start"))
async def cmd_start(m: Message):
    if m.from_user.id in ADMIN_IDS:
        await clear_state(m.from_user.id)
    await show_welcome(m.from_user.id)
    if m.from_user.id in ADMIN_IDS:
        await m.answer("🛠 Siz adminsiz — admin panel: /admin")


@r.message(Command("admin"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_admin(m: Message):
    await clear_state(m.from_user.id)
    await send_menu(m.from_user.id)


@r.message(Command("cancel"))
async def cmd_cancel(m: Message):
    uid = m.from_user.id
    if uid in ADMIN_IDS and await get_state(uid):
        await clear_state(uid)
        await m.answer("❎ Bekor qilindi.")
        return await send_menu(uid)
    await run("UPDATE orders SET status='cancelled' WHERE user_id=? AND status IN ('promo','promo_in','receipt','videos')", uid)
    await m.answer("❎ Bekor qilindi. Qayta boshlash: /start")


@r.callback_query(F.data == "chk")
async def on_chk(c: CallbackQuery):
    miss = await missing_channels(c.from_user.id)
    if miss:
        return await c.answer("Hali hamma kanalga obuna bo'lmagansiz ❗️", show_alert=True)
    await c.answer("✅ Rahmat!")
    try:
        await c.message.delete()
    except Exception:
        pass
    await show_welcome(c.from_user.id)


@r.callback_query(F.data == "next")
async def on_next(c: CallbackQuery):
    await c.answer()
    uid = c.from_user.id
    try:
        await c.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if await gs("orders_open") != "1":
        return await safe_send(uid, await render("closed_text"))
    if not await gs("card"):
        return await safe_send(uid, "⚠️ To'lov ma'lumotlari hali kiritilmagan. Keyinroq urinib ko'ring.")
    await run("UPDATE orders SET status='cancelled' WHERE user_id=? AND status IN ('promo','promo_in','receipt','videos')", uid)
    oid, _ = await run(
        "INSERT INTO orders(user_id,status,price,created_at) VALUES(?,?,?,?)",
        uid,
        "promo",
        int(await gs("price") or 0),
        int(time.time()),
    )
    has_promo = (await one("SELECT COUNT(*) FROM promos WHERE active=1"))[0]
    if not has_promo:
        return await pay_step(uid, oid)
    await safe_send(uid, PROMO_ASK, markup=promo_kb())


PROMO_ASK = (
    "🎟 <b>Promokodingiz bormi?</b>\n\n"
    "Promokod bo'lsa chegirma olasiz. Bo'lmasa, «Promokodsiz davom etish» tugmasini bosing."
)


def promo_kb():
    return kb(
        [("🎟 Promokod kiritish", "pc:enter")],
        [("➡️ Promokodsiz davom etish", "pc:skip")],
        [("❌ Bekor qilish", "ucancel")],
    )


async def cur_promo_order(uid):
    return await one(
        "SELECT * FROM orders WHERE user_id=? AND status IN ('promo','promo_in') ORDER BY id DESC LIMIT 1",
        uid,
    )


async def pay_step(uid, oid):
    """To'lov bosqichiga o'tish (promokod bosqichidan keyin yoki promokod yo'q bo'lsa)."""
    _, n = await run(
        "UPDATE orders SET status='receipt' WHERE id=? AND status IN ('promo','promo_in')", oid
    )
    if not n:
        return
    o = await one("SELECT * FROM orders WHERE id=?", oid)
    text = await render("pay_text", oid)
    if o["promo_code"]:
        text = (
            f"🎟 Promokod <b>{html.escape(o['promo_code'])}</b> qo'llanildi: <b>-{o['promo_percent']}%</b>\n"
            f"Narx: <s>{fmt(await gs('price'))}</s> → <b>{fmt(o['price'])} so'm</b>\n\n" + text
        )
    await safe_send(
        uid,
        text,
        await gs("pay_photo") or None,
        kb([("❌ Bekor qilish", "ucancel")]),
    )


@r.callback_query(F.data == "pc:enter")
async def pc_enter(c: CallbackQuery):
    o = await cur_promo_order(c.from_user.id)
    if not o:
        return await c.answer("Buyurtma topilmadi. /start ni bosing", show_alert=True)
    await run("UPDATE orders SET status='promo_in' WHERE id=?", o["id"])
    await c.answer()
    await show(
        c,
        "🎟 <b>Promokodni yozib yuboring</b>\n\nMasalan: <code>ABE20</code>",
        kb([("➡️ Promokodsiz davom etish", "pc:skip")], [("❌ Bekor qilish", "ucancel")]),
    )


@r.callback_query(F.data == "pc:skip")
async def pc_skip(c: CallbackQuery):
    o = await cur_promo_order(c.from_user.id)
    if not o:
        return await c.answer("Buyurtma topilmadi. /start ni bosing", show_alert=True)
    await c.answer()
    try:
        await c.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await pay_step(c.from_user.id, o["id"])


async def apply_promo(m: Message, o):
    code = (m.text or "").strip().upper()
    p = await one("SELECT * FROM promos WHERE code=? AND active=1", code) if code else None
    if not p:
        return await m.answer(
            "❌ Bunday promokod topilmadi yoki faol emas.\nQayta yozing yoki davom eting 👇",
            reply_markup=kb([("➡️ Promokodsiz davom etish", "pc:skip")], [("❌ Bekor qilish", "ucancel")]),
        )
    base = int(await gs("price") or 0)
    new_price = max(base * (100 - p["percent"]) // 100, 1)
    await run(
        "UPDATE orders SET promo_code=?, promo_percent=?, price=? WHERE id=?",
        p["code"],
        p["percent"],
        new_price,
        o["id"],
    )
    await pay_step(m.from_user.id, o["id"])


@r.callback_query(F.data == "ucancel")
async def on_ucancel(c: CallbackQuery):
    await run("UPDATE orders SET status='cancelled' WHERE user_id=? AND status IN ('promo','promo_in','receipt','videos')", c.from_user.id)
    await c.answer("Bekor qilindi")
    try:
        await c.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await c.message.answer("❎ Buyurtma bekor qilindi. Qayta boshlash: /start")


_deb: dict = {}


def schedule_prompt(oid):
    t = _deb.get(oid)
    if t:
        t.cancel()
    _deb[oid] = asyncio.create_task(_upd_prompt(oid))


async def _upd_prompt(oid):
    try:
        await asyncio.sleep(1.2)
    except asyncio.CancelledError:
        return
    o = await one("SELECT * FROM orders WHERE id=?", oid)
    if not o or o["status"] != "videos":
        return
    if o["prompt_msg_id"]:
        try:
            await bot.delete_message(o["user_id"], o["prompt_msg_id"])
        except Exception:
            pass
    msg = await safe_send(
        o["user_id"],
        f"🎬 Qabul qilindi: <b>{o['video_count']} ta</b> video.\n"
        "Yana yuborishingiz mumkin. Tugatgan bo'lsangiz tugmani bosing 👇",
        markup=kb([("✅ Yuborib bo'ldim", "vdone")], [("❌ Bekor qilish", "ucancel")]),
    )
    if msg:
        await run("UPDATE orders SET prompt_msg_id=? WHERE id=?", msg.message_id, oid)


class HasState(BaseFilter):
    """Admin biror amal (video yuborish, rasm yuklash va h.k.) holatida ekanini tekshiradi."""

    async def __call__(self, message: Message) -> bool:
        return (
            bool(message.from_user)
            and message.from_user.id in ADMIN_IDS
            and await get_state(message.from_user.id) is not None
        )


@r.message(
    F.chat.type == "private",
    invert_f(HasState()),
    F.photo | F.video | F.video_note | F.document | F.animation,
)
async def on_media(m: Message):
    uid = m.from_user.id
    o = await draft(uid)
    if not o:
        return await m.answer("Buyurtma berish uchun /start ni bosing 👇")
    mime = (m.document.mime_type or "") if m.document else ""
    is_video = bool(m.video or m.video_note or m.animation or mime.startswith("video/"))

    if o["status"] == "receipt":
        if m.photo:
            rid, kind = m.photo[-1].file_id, "photo"
        elif m.document and (mime.startswith("image/") or mime == "application/pdf"):
            rid, kind = m.document.file_id, "document"
        else:
            return await m.answer("🧾 Avval to'lov <b>chekini</b> rasm qilib yuboring.")
        await run(
            "UPDATE orders SET receipt_id=?, receipt_kind=?, status='videos' WHERE id=?",
            rid,
            kind,
            o["id"],
        )
        return await send(
            uid,
            await render("videos_text", o["id"]),
            markup=kb([("❌ Bekor qilish", "ucancel")]),
        )

    if o["status"] in ("promo", "promo_in"):
        return await m.answer(
            "🎟 Avval promokod bosqichini yakunlang:", reply_markup=promo_kb()
        )

    # status == videos
    if not is_video:
        return await m.answer("🎬 Hozir <b>video</b> yuboring (chek allaqachon qabul qilingan).")
    await run(
        "INSERT INTO order_videos(order_id,user_msg_id) VALUES(?,?)", o["id"], m.message_id
    )
    await run("UPDATE orders SET video_count=video_count+1 WHERE id=?", o["id"])
    schedule_prompt(o["id"])


@r.callback_query(F.data == "vdone")
async def on_vdone(c: CallbackQuery):
    o = await one(
        "SELECT * FROM orders WHERE user_id=? AND status='videos' ORDER BY id DESC LIMIT 1",
        c.from_user.id,
    )
    if not o:
        return await c.answer("Faol buyurtma yo'q", show_alert=True)
    if o["video_count"] < 1:
        return await c.answer("Kamida 1 ta video yuboring", show_alert=True)
    t = _deb.pop(o["id"], None)
    if t:
        t.cancel()
    await c.answer()
    try:
        await c.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if await submit_order(o):
        await safe_send(c.from_user.id, await render("submitted_text", o["id"]))
    else:
        await c.message.answer("⚠️ Xatolik yuz berdi. Iltimos, birozdan so'ng «✅ Yuborib bo'ldim» ni qayta bosing.")


# ----------------------------------------------------------------------------
# KANAL / ADMIN: tasdiqlash, rad etish, tayyor video
# ----------------------------------------------------------------------------
@r.callback_query(F.data.regexp(r"^(ok|no):\d+$"))
async def on_decide(c: CallbackQuery):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer("Siz admin emassiz", show_alert=True)
    act, oid = c.data.split(":")
    oid = int(oid)
    done = await decide(oid, act == "ok", c.from_user.id)
    if not done:
        return await c.answer("Bu buyurtma allaqachon ko'rib chiqilgan", show_alert=True)
    await c.answer("✅ Tasdiqlandi" if act == "ok" else "❌ Rad etildi")
    if c.message.chat.type == "private":
        await show_order(c, oid)


@r.callback_query(F.data.regexp(r"^send:\d+$"))
async def on_send(c: CallbackQuery):
    if c.from_user.id not in ADMIN_IDS:
        return await c.answer("Siz admin emassiz", show_alert=True)
    oid = int(c.data.split(":")[1])
    o = await one("SELECT * FROM orders WHERE id=?", oid)
    if not o or o["status"] not in ("approved", "done"):
        return await c.answer("Buyurtma tasdiqlanmagan", show_alert=True)
    await set_state(c.from_user.id, f"deliver:{oid}", {"sent": 0})
    try:
        await bot.send_message(
            c.from_user.id,
            f"📤 <b>Buyurtma #{oid}</b> uchun tayyor videoni shu yerga yuboring.\n"
            "Bir nechta yuborishingiz mumkin. Tugagach «✅ Yakunlash» ni bosing.",
            reply_markup=kb([("✅ Yakunlash", f"fin:{oid}")], [("🚫 Bekor", "a:cancel")]),
        )
    except TelegramForbiddenError:
        await clear_state(c.from_user.id)
        return await c.answer("Avval botga o'tib /start bosing", show_alert=True)
    await c.answer("Bot lichkasiga qarang 👇")


@r.callback_query(F.data.regexp(r"^fin:\d+$"), F.from_user.id.in_(ADMIN_IDS))
async def on_finish(c: CallbackQuery):
    oid = int(c.data.split(":")[1])
    st = await get_state(c.from_user.id)
    if not st or st[0] != f"deliver:{oid}" or st[1].get("sent", 0) < 1:
        return await c.answer("Hali video yuborilmagan", show_alert=True)
    await clear_state(c.from_user.id)
    await run("UPDATE orders SET status='done' WHERE id=? AND status='approved'", oid)
    await refresh_card(oid)
    await c.answer("Yakunlandi ✅")
    await show(c, f"✅ Buyurtma #{oid} yakunlandi. Mijozga {st[1]['sent']} ta video yuborildi.")
    await send_menu(c.from_user.id)


# ----------------------------------------------------------------------------
# ADMIN PANEL
# ----------------------------------------------------------------------------
async def menu_view():
    price = fmt(await gs("price"))
    card = await gs("card")
    holder = await gs("holder")
    opened = await gs("orders_open") == "1"
    st = "🟢 yoqilgan" if opened else "🔴 o'chirilgan"
    card_s = html.escape(card) if card else "—"
    text = (
        "🛠 <b>Admin panel</b>\n\n"
        f"💰 Narx: <b>{price} so'm</b>\n"
        f"💳 Karta: <code>{card_s}</code> ({html.escape(holder) or '—'})\n"
        f"📦 Buyurtma qabul qilish: {st}"
    )
    toggle = "🔴 Buyurtmani to'xtatish" if opened else "🟢 Buyurtmani yoqish"
    markup = kb(
        [("📊 Statistika", "a:stats"), ("📋 Buyurtmalar", "a:orders:pending")],
        [("📣 Xabar yuborish", "a:bc"), ("📢 Majburiy obuna", "a:chs")],
        [("💰 Narx", "a:price"), ("💳 Karta", "a:card")],
        [("✏️ Matnlar", "a:texts"), ("🖼 Rasmlar", "a:photos")],
        [("🎟 Promokodlar", "a:promos")],
        [(toggle, "a:toggle")],
    )
    return text, markup


async def send_menu(uid):
    text, markup = await menu_view()
    await bot.send_message(uid, text, reply_markup=markup)


BACK = [("🔙 Menyu", "a:menu")]


@r.callback_query(F.data == "a:menu", F.from_user.id.in_(ADMIN_IDS))
async def a_menu(c: CallbackQuery):
    await clear_state(c.from_user.id)
    await c.answer()
    text, markup = await menu_view()
    await show(c, text, markup)


@r.callback_query(F.data == "a:cancel", F.from_user.id.in_(ADMIN_IDS))
async def a_cancel(c: CallbackQuery):
    await clear_state(c.from_user.id)
    await c.answer("Bekor qilindi")
    text, markup = await menu_view()
    await show(c, text, markup)


@r.callback_query(F.data == "a:toggle", F.from_user.id.in_(ADMIN_IDS))
async def a_toggle(c: CallbackQuery):
    await ss("orders_open", "0" if await gs("orders_open") == "1" else "1")
    await c.answer("Saqlandi")
    text, markup = await menu_view()
    await show(c, text, markup)


# --- statistika ---
@r.callback_query(F.data == "a:stats", F.from_user.id.in_(ADMIN_IDS))
async def a_stats(c: CallbackQuery):
    await c.answer()
    d = datetime.now(TZ)
    day0 = int(d.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    week0 = day0 - 6 * 86400
    month0 = int(d.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())

    async def n(sql, *a):
        row = await one(sql, *a)
        return (row[0] or 0) if row else 0

    users = await n("SELECT COUNT(*) FROM users")
    active = await n("SELECT COUNT(*) FROM users WHERE active=1")
    u_today = await n("SELECT COUNT(*) FROM users WHERE joined_at>=?", day0)
    u_week = await n("SELECT COUNT(*) FROM users WHERE joined_at>=?", week0)
    sub = "('pending','approved','rejected','done')"
    total = await n(f"SELECT COUNT(*) FROM orders WHERE status IN {sub}")
    today = await n("SELECT COUNT(*) FROM orders WHERE submitted_at>=?", day0)
    cnt = {}
    for s in ("pending", "approved", "done", "rejected"):
        cnt[s] = await n("SELECT COUNT(*) FROM orders WHERE status=?", s)
    paid = "('approved','done')"
    rev = await n(f"SELECT SUM(price) FROM orders WHERE status IN {paid}")
    rev_t = await n(f"SELECT SUM(price) FROM orders WHERE status IN {paid} AND decided_at>=?", day0)
    rev_m = await n(f"SELECT SUM(price) FROM orders WHERE status IN {paid} AND decided_at>=?", month0)
    text = (
        "📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: <b>{users}</b> (faol: {active})\n"
        f"   • Bugun: +{u_today}   • 7 kun: +{u_week}\n\n"
        f"📦 Buyurtmalar: <b>{total}</b> (bugun: {today})\n"
        f"   • ⏳ Kutilmoqda: {cnt['pending']}\n"
        f"   • ✅ Montajda: {cnt['approved']}\n"
        f"   • 📦 Yakunlangan: {cnt['done']}\n"
        f"   • ❌ Rad etilgan: {cnt['rejected']}\n\n"
        f"💰 Tushum: <b>{fmt(rev)} so'm</b>\n"
        f"   • Bugun: {fmt(rev_t)}   • Shu oy: {fmt(rev_m)}"
    )
    await show(c, text, kb(BACK))


# --- buyurtmalar ---
FILTERS = {
    "pending": "⏳ Kutilmoqda",
    "approved": "✅ Montajda",
    "done": "📦 Yakun",
    "rejected": "❌ Rad",
    "all": "📋 Hammasi",
}


@r.callback_query(F.data.regexp(r"^a:orders:\w+$"), F.from_user.id.in_(ADMIN_IDS))
async def a_orders(c: CallbackQuery):
    await c.answer()
    flt = c.data.split(":")[2]
    if flt == "all":
        rows = await fetch(
            "SELECT * FROM orders WHERE status IN ('pending','approved','rejected','done') ORDER BY id DESC LIMIT 15"
        )
    else:
        rows = await fetch("SELECT * FROM orders WHERE status=? ORDER BY id DESC LIMIT 15", flt)
    btns = []
    keys = list(FILTERS.items())
    btns.append([(("• " if k == flt else "") + v, f"a:orders:{k}") for k, v in keys[:3]])
    btns.append([(("• " if k == flt else "") + v, f"a:orders:{k}") for k, v in keys[3:]])
    for o in rows:
        btns.append([(f"{EMO[o['status']]} #{o['id']} · {fmt(o['price'])} · {fdt(o['submitted_at'])}", f"a:ord:{o['id']}")])
    btns.append(BACK)
    text = f"📋 <b>Buyurtmalar</b> — {FILTERS[flt]}" + ("" if rows else "\n\nBo'sh.")
    await show(c, text, kb(*btns))


async def show_order(c: CallbackQuery, oid):
    o = await one("SELECT * FROM orders WHERE id=?", oid)
    if not o:
        return await c.answer("Topilmadi", show_alert=True)
    u = await one("SELECT * FROM users WHERE id=?", o["user_id"])
    text = card_caption(o, u) if o["submitted_at"] else f"Buyurtma #{oid}: {STATUS.get(o['status'])}"
    rows = []
    if o["status"] == "pending":
        rows.append([("✅ Tasdiqlash", f"ok:{oid}"), ("❌ Rad etish", f"no:{oid}")])
    if o["status"] in ("approved", "done"):
        rows.append([("📤 Tayyor videoni yuborish", f"send:{oid}")])
    if o["receipt_id"]:
        rows.append([("🧾 Chek", f"a:rc:{oid}"), ("🎬 Videolar", f"a:vd:{oid}")])
    rows.append([("🔙 Ro'yxat", "a:orders:pending")])
    await show(c, text, kb(*rows))


@r.callback_query(F.data.regexp(r"^a:ord:\d+$"), F.from_user.id.in_(ADMIN_IDS))
async def a_ord(c: CallbackQuery):
    await c.answer()
    await show_order(c, int(c.data.split(":")[2]))


@r.callback_query(F.data.regexp(r"^a:rc:\d+$"), F.from_user.id.in_(ADMIN_IDS))
async def a_receipt(c: CallbackQuery):
    o = await one("SELECT * FROM orders WHERE id=?", int(c.data.split(":")[2]))
    await c.answer()
    if o and o["receipt_id"]:
        if o["receipt_kind"] == "photo":
            await bot.send_photo(c.from_user.id, o["receipt_id"], caption=f"🧾 Chek — #{o['id']}")
        else:
            await bot.send_document(c.from_user.id, o["receipt_id"], caption=f"🧾 Chek — #{o['id']}")


@r.callback_query(F.data.regexp(r"^a:vd:\d+$"), F.from_user.id.in_(ADMIN_IDS))
async def a_videos(c: CallbackQuery):
    oid = int(c.data.split(":")[2])
    o = await one("SELECT * FROM orders WHERE id=?", oid)
    await c.answer()
    for v in await fetch("SELECT * FROM order_videos WHERE order_id=? ORDER BY id", oid):
        try:
            if v["ch_msg_id"] and CHANNEL_ID:
                await copy_retry(c.from_user.id, CHANNEL_ID, v["ch_msg_id"])
            else:
                await copy_retry(c.from_user.id, o["user_id"], v["user_msg_id"])
        except Exception as e:
            log.warning("a_videos: %s", e)
        await asyncio.sleep(0.2)


# --- narx / karta ---
@r.callback_query(F.data == "a:price", F.from_user.id.in_(ADMIN_IDS))
async def a_price(c: CallbackQuery):
    await set_state(c.from_user.id, "price")
    await c.answer()
    await show(
        c,
        f"💰 Hozirgi narx: <b>{fmt(await gs('price'))} so'm</b>\n\nYangi narxni raqam bilan yuboring (masalan: <code>50000</code>)",
        kb([("🚫 Bekor", "a:cancel")]),
    )


@r.callback_query(F.data == "a:card", F.from_user.id.in_(ADMIN_IDS))
async def a_card(c: CallbackQuery):
    await set_state(c.from_user.id, "card")
    await c.answer()
    card = await gs("card")
    await show(
        c,
        f"💳 Hozirgi karta: <code>{html.escape(card) if card else '—'}</code>\n\n1/2 — Yangi <b>karta raqamini</b> yuboring:",
        kb([("🚫 Bekor", "a:cancel")]),
    )


# --- matnlar ---
@r.callback_query(F.data == "a:texts", F.from_user.id.in_(ADMIN_IDS))
async def a_texts(c: CallbackQuery):
    await c.answer()
    rows = [[(label, f"a:text:{k}")] for k, label in TEXT_KEYS]
    rows.append(BACK)
    await show(c, "✏️ <b>Qaysi matnni o'zgartirasiz?</b>", kb(*rows))


@r.callback_query(F.data.regexp(r"^a:text:\w+$"), F.from_user.id.in_(ADMIN_IDS))
async def a_text(c: CallbackQuery):
    key = c.data.split(":")[2]
    if key not in dict(TEXT_KEYS):
        return await c.answer()
    await set_state(c.from_user.id, f"text:{key}")
    await c.answer()
    await show(
        c,
        "Hozirgi matn pastda 👇\n\nYangi matnni yuboring (formatlash — qalin, kursiv va h.k. saqlanadi).\n"
        "Belgilar: <code>{price}</code> narx, <code>{card}</code> karta, <code>{holder}</code> karta egasi, "
        "<code>{id}</code> buyurtma raqami.",
        kb([("🚫 Bekor", "a:cancel")]),
    )
    try:
        await send(c.from_user.id, await gs(key))
    except Exception:
        await bot.send_message(c.from_user.id, await gs(key), parse_mode=None)


# --- rasmlar ---
@r.callback_query(F.data == "a:photos", F.from_user.id.in_(ADMIN_IDS))
async def a_photos(c: CallbackQuery):
    await c.answer()
    rows = []
    for k, label in PHOTO_KEYS:
        mark = "✅" if await gs(k) else "➖"
        rows.append([(f"{mark} {label}", f"a:photo:{k}")])
    rows.append(BACK)
    await show(c, "🖼 <b>Rasmlar</b>\n\nBot xabarlariga rasm qo'shish uchun tanlang:", kb(*rows))


@r.callback_query(F.data.regexp(r"^a:photo:\w+$"), F.from_user.id.in_(ADMIN_IDS))
async def a_photo(c: CallbackQuery):
    key = c.data.split(":")[2]
    if key not in dict(PHOTO_KEYS):
        return await c.answer()
    await set_state(c.from_user.id, f"photo:{key}")
    await c.answer()
    await show(
        c,
        "Yangi <b>rasmni</b> yuboring (rasm sifatida).",
        kb([("🗑 Rasmni o'chirish", f"a:pdel:{key}")], [("🚫 Bekor", "a:cancel")]),
    )


@r.callback_query(F.data.regexp(r"^a:pdel:\w+$"), F.from_user.id.in_(ADMIN_IDS))
async def a_pdel(c: CallbackQuery):
    key = c.data.split(":")[2]
    if key in dict(PHOTO_KEYS):
        await ss(key, "")
    await clear_state(c.from_user.id)
    await c.answer("O'chirildi")
    text, markup = await menu_view()
    await show(c, text, markup)


# --- majburiy obuna ---
@r.callback_query(F.data == "a:chs", F.from_user.id.in_(ADMIN_IDS))
async def a_chs(c: CallbackQuery):
    await c.answer()
    chans = await fetch("SELECT * FROM channels ORDER BY added_at")
    rows = [[(f"🗑 {ch['title']}", f"a:chdel:{ch['id']}")] for ch in chans]
    rows.append([("➕ Kanal qo'shish", "a:chadd")])
    rows.append(BACK)
    text = (
        "📢 <b>Majburiy obuna kanallari</b>\n\n"
        + ("Quyidagi kanallarga obuna bo'lmagan foydalanuvchi botdan foydalana olmaydi.\nO'chirish uchun kanal nomini bosing."
           if chans else "Hozircha kanal yo'q. Reklama tushsa, shu yerdan kanalni qo'shing.")
    )
    await show(c, text, kb(*rows))


@r.callback_query(F.data == "a:chadd", F.from_user.id.in_(ADMIN_IDS))
async def a_chadd(c: CallbackQuery):
    await set_state(c.from_user.id, "addch")
    await c.answer()
    await show(
        c,
        "➕ <b>Kanal qo'shish</b>\n\n1️⃣ Botni o'sha kanalga <b>admin</b> qiling\n"
        "2️⃣ Kanaldan istalgan postni shu yerga <b>forward</b> qiling\n"
        "yoki <code>@username</code> / ID (<code>-100...</code>) yuboring.",
        kb([("🚫 Bekor", "a:cancel")]),
    )


@r.callback_query(F.data.regexp(r"^a:chdel:-?\d+$"), F.from_user.id.in_(ADMIN_IDS))
async def a_chdel(c: CallbackQuery):
    await run("DELETE FROM channels WHERE id=?", int(c.data.split(":", 2)[2]))
    await a_chs(c)


# --- promokodlar ---
@r.callback_query(F.data == "a:promos", F.from_user.id.in_(ADMIN_IDS))
async def a_promos(c: CallbackQuery):
    await c.answer()
    await clear_state(c.from_user.id)
    ps = await fetch("SELECT * FROM promos ORDER BY created_at DESC")
    btns = [
        [(f"{'🟢' if p['active'] else '🔴'} {p['code']} — {p['percent']}% · {p['used']} ta", f"a:prv:{p['code']}")]
        for p in ps
    ]
    btns.append([("➕ Promokod qo'shish", "a:pradd")])
    btns.append(BACK)
    text = "🎟 <b>Promokodlar</b>\n\n" + (
        "Promokodni bosib o'zgartirish, o'chirish yoki to'xtatish mumkin.\n"
        "Raqam — necha marta ishlatilgani."
        if ps
        else "Hozircha promokod yo'q. Promokod bo'lmasa, mijozlarga promokod so'ralmaydi."
    )
    await show(c, text, kb(*btns))


@r.callback_query(F.data == "a:pradd", F.from_user.id.in_(ADMIN_IDS))
async def a_pradd(c: CallbackQuery):
    await set_state(c.from_user.id, "pcode")
    await c.answer()
    await show(
        c,
        "➕ <b>Yangi promokod</b>\n\n1/2 — Promokodni yozing (harf va raqam, 3-20 belgi).\nMasalan: <code>ABE20</code>",
        kb([("🚫 Bekor", "a:promos")]),
    )


async def promo_view(c: CallbackQuery, code):
    p = await one("SELECT * FROM promos WHERE code=?", code)
    if not p:
        return await show(c, "Promokod topilmadi.", kb([("🔙 Promokodlar", "a:promos")]))
    text = (
        f"🎟 <b>{html.escape(p['code'])}</b>\n\n"
        f"Chegirma: <b>{p['percent']}%</b>\n"
        f"Ishlatilgan: <b>{p['used']}</b> ta\n"
        f"Holat: {'🟢 faol' if p['active'] else '🔴 to`xtatilgan'}"
    )
    await show(
        c,
        text,
        kb(
            [("🔴 To'xtatish" if p["active"] else "🟢 Yoqish", f"a:prt:{code}")],
            [("✏️ Foizni o'zgartirish", f"a:pre:{code}")],
            [("🗑 O'chirish", f"a:prd:{code}")],
            [("🔙 Promokodlar", "a:promos")],
        ),
    )


@r.callback_query(F.data.regexp(r"^a:prv:[A-Z0-9_-]+$"), F.from_user.id.in_(ADMIN_IDS))
async def a_prv(c: CallbackQuery):
    await c.answer()
    await promo_view(c, c.data.split(":")[2])


@r.callback_query(F.data.regexp(r"^a:prt:[A-Z0-9_-]+$"), F.from_user.id.in_(ADMIN_IDS))
async def a_prt(c: CallbackQuery):
    code = c.data.split(":")[2]
    await run("UPDATE promos SET active=1-active WHERE code=?", code)
    await c.answer("Saqlandi")
    await promo_view(c, code)


@r.callback_query(F.data.regexp(r"^a:pre:[A-Z0-9_-]+$"), F.from_user.id.in_(ADMIN_IDS))
async def a_pre(c: CallbackQuery):
    code = c.data.split(":")[2]
    await set_state(c.from_user.id, "ppct", {"code": code})
    await c.answer()
    await show(
        c,
        f"✏️ <b>{html.escape(code)}</b> uchun yangi chegirma foizini yozing (1 dan 99 gacha).",
        kb([("🚫 Bekor", f"a:prv:{code}")]),
    )


@r.callback_query(F.data.regexp(r"^a:prd:[A-Z0-9_-]+$"), F.from_user.id.in_(ADMIN_IDS))
async def a_prd(c: CallbackQuery):
    await run("DELETE FROM promos WHERE code=?", c.data.split(":")[2])
    await a_promos(c)


# --- xabar yuborish ---
@r.callback_query(F.data == "a:bc", F.from_user.id.in_(ADMIN_IDS))
async def a_bc(c: CallbackQuery):
    await set_state(c.from_user.id, "bc")
    await c.answer()
    n = (await one("SELECT COUNT(*) FROM users WHERE active=1"))[0]
    await show(
        c,
        f"📣 <b>Xabar yuborish</b>\n\nFaol foydalanuvchilar: <b>{n}</b>\n\n"
        "Yuboriladigan xabarni shu yerga yuboring (matn, rasm, video — istalgani, formatlash bilan).",
        kb([("🚫 Bekor", "a:cancel")]),
    )


@r.callback_query(F.data == "a:bcgo", F.from_user.id.in_(ADMIN_IDS))
async def a_bcgo(c: CallbackQuery):
    st = await get_state(c.from_user.id)
    if not st or st[0] != "bc2":
        return await c.answer("Xabar topilmadi", show_alert=True)
    await clear_state(c.from_user.id)
    await c.answer("Yuborish boshlandi 🚀")
    await show(c, "🚀 Yuborilmoqda... Tugagach hisobot keladi.")
    asyncio.create_task(broadcast(c.from_user.id, st[1]["chat"], st[1]["msg"]))


async def broadcast(admin_id, chat, msg):
    users = await fetch("SELECT id FROM users WHERE active=1")
    ok = bad = 0
    for u in users:
        try:
            await copy_retry(u["id"], chat, msg)
            ok += 1
        except TelegramForbiddenError:
            await run("UPDATE users SET active=0 WHERE id=?", u["id"])
            bad += 1
        except Exception:
            bad += 1
        await asyncio.sleep(0.05)
    await safe_send(
        admin_id, f"📣 <b>Xabar yuborish tugadi</b>\n\n✅ Yetkazildi: {ok}\n❌ Yetmadi (bloklagan): {bad}"
    )


# --- admin matn/rasm/video kiritishi (holat bo'yicha) ---
async def _finish(uid, text):
    await clear_state(uid)
    await bot.send_message(uid, text)
    await send_menu(uid)


@r.message(F.chat.type == "private", HasState())
async def admin_input(m: Message):
    uid = m.from_user.id
    action, data = await get_state(uid)

    if action == "price":
        digits = re.sub(r"\D", "", m.text or "")
        if not digits or int(digits) <= 0:
            return await m.answer("❗️ Faqat raqam yuboring, masalan: <code>50000</code>")
        await ss("price", digits)
        return await _finish(uid, f"✅ Narx saqlandi: <b>{fmt(digits)} so'm</b>")

    if action == "card":
        if not m.text:
            return await m.answer("❗️ Karta raqamini matn qilib yuboring.")
        await ss("card", m.text.strip())
        await set_state(uid, "holder")
        return await m.answer("2/2 — <b>Karta egasining ism-familiyasini</b> yuboring:")

    if action == "holder":
        if not m.text:
            return await m.answer("❗️ Matn yuboring.")
        await ss("holder", m.text.strip())
        return await _finish(uid, "✅ Karta ma'lumotlari saqlandi.")

    if action.startswith("text:"):
        key = action.split(":", 1)[1]
        if not m.text:
            return await m.answer("❗️ Matn yuboring.")
        val = m.html_text
        try:
            await bot.send_message(uid, "👁 <b>Ko'rinishi:</b>\n\n" + fill(val))
        except TelegramBadRequest as e:
            return await m.answer(f"❗️ HTML formatda xato: <code>{html.escape(str(e))}</code>\nQayta yuboring.")
        await ss(key, val)
        return await _finish(uid, "✅ Matn saqlandi.")

    if action.startswith("photo:"):
        key = action.split(":", 1)[1]
        if not m.photo:
            return await m.answer("❗️ Rasmni <b>rasm</b> sifatida yuboring.")
        await ss(key, m.photo[-1].file_id)
        return await _finish(uid, "✅ Rasm saqlandi.")

    if action == "addch":
        chat_id = None
        fo = getattr(m, "forward_origin", None)
        if fo is not None and getattr(fo, "chat", None) is not None:
            chat_id = fo.chat.id
        elif getattr(m, "forward_from_chat", None):
            chat_id = m.forward_from_chat.id
        elif m.text:
            t = m.text.strip()
            if t.startswith("https://t.me/") or t.startswith("t.me/"):
                t = "@" + t.rstrip("/").split("/")[-1]
            if t.lstrip("-").isdigit():
                chat_id = int(t)
            elif t.startswith("@"):
                chat_id = t
        if chat_id is None:
            return await m.answer("❗️ Kanaldan post forward qiling yoki @username / ID yuboring.")
        try:
            ch = await bot.get_chat(chat_id)
            me = await bot.get_chat_member(ch.id, BOT_ID)
        except Exception as e:
            return await m.answer(
                f"❗️ Kanal topilmadi yoki bot unda yo'q.\n<code>{html.escape(str(e))}</code>"
            )
        if me.status not in ("administrator", "creator"):
            return await m.answer("❗️ Bot bu kanalda <b>admin emas</b>. Avval botni admin qiling, so'ng qayta yuboring.")
        link = f"https://t.me/{ch.username}" if ch.username else ""
        if not link:
            try:
                link = (await bot.create_chat_invite_link(ch.id)).invite_link
            except Exception:
                link = ch.invite_link or ""
        await run(
            "INSERT OR REPLACE INTO channels(id,title,link,added_at) VALUES(?,?,?,?)",
            ch.id,
            ch.title or str(ch.id),
            link,
            int(time.time()),
        )
        return await _finish(uid, f"✅ Kanal qo'shildi: <b>{html.escape(ch.title or '')}</b>")

    if action == "pcode":
        code = (m.text or "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9_-]{3,20}", code):
            return await m.answer("❗️ Promokod 3-20 belgi bo'lsin: faqat harf, raqam, - yoki _. Qayta yozing.")
        await set_state(uid, "ppct", {"code": code})
        ex = await one("SELECT percent FROM promos WHERE code=?", code)
        note = f"\n(Bu promokod bor edi — {ex['percent']}%, yangisi bilan almashadi.)" if ex else ""
        return await m.answer(
            f"2/2 — <b>{html.escape(code)}</b> necha foiz chegirma bersin? (1 dan 99 gacha, masalan: <code>20</code>){note}"
        )

    if action == "ppct":
        digits = re.sub(r"\D", "", m.text or "")
        if not digits or not (1 <= int(digits) <= 99):
            return await m.answer("❗️ 1 dan 99 gacha raqam yozing, masalan: <code>20</code>")
        code = data["code"]
        await run(
            "INSERT INTO promos(code,percent,active,used,created_at) VALUES(?,?,1,0,?) "
            "ON CONFLICT(code) DO UPDATE SET percent=excluded.percent",
            code,
            int(digits),
            int(time.time()),
        )
        await clear_state(uid)
        await m.answer(f"✅ Promokod saqlandi: <b>{html.escape(code)}</b> — <b>{int(digits)}%</b> chegirma")
        return await bot.send_message(
            uid, "🎟 Promokodlar:", reply_markup=kb([("🎟 Promokodlarga o'tish", "a:promos")], BACK)
        )

    if action == "bc":
        await set_state(uid, "bc2", {"chat": m.chat.id, "msg": m.message_id})
        n = (await one("SELECT COUNT(*) FROM users WHERE active=1"))[0]
        return await m.reply(
            f"☝️ Shu xabar <b>{n}</b> ta foydalanuvchiga yuboriladi. Tasdiqlaysizmi?",
            reply_markup=kb([("🚀 Yuborish", "a:bcgo")], [("🚫 Bekor", "a:cancel")]),
        )

    if action == "bc2":
        return await m.answer("Yuborish yoki bekor qilish tugmasini bosing 👆")

    if action.startswith("deliver:"):
        oid = int(action.split(":")[1])
        o = await one("SELECT * FROM orders WHERE id=?", oid)
        mime = (m.document.mime_type or "") if m.document else ""
        if not (m.video or m.video_note or m.animation or m.document):
            return await m.answer("❗️ Tayyor videoni (yoki fayl) yuboring.")
        kw = {}
        if not m.video_note:
            kw["caption"] = await render("done_text", oid)
        try:
            await copy_retry(o["user_id"], m.chat.id, m.message_id, **kw)
        except TelegramForbiddenError:
            return await m.answer("❗️ Mijoz botni bloklagan, yuborib bo'lmadi.")
        except TelegramBadRequest:
            await copy_retry(o["user_id"], m.chat.id, m.message_id)
        data["sent"] = data.get("sent", 0) + 1
        await set_state(uid, action, data)
        return await m.answer(
            f"✅ Mijozga yuborildi ({data['sent']}). Yana yuborishingiz yoki yakunlashingiz mumkin.",
            reply_markup=kb([("✅ Yakunlash", f"fin:{oid}")]),
        )

    await clear_state(uid)


# ----------------------------------------------------------------------------
# Qolgan xabarlar
# ----------------------------------------------------------------------------
@r.message(F.chat.type == "private")
async def fallback(m: Message):
    o = await draft(m.from_user.id)
    if o and o["status"] == "promo_in" and m.text:
        return await apply_promo(m, o)
    if o and o["status"] == "promo":
        return await m.answer("🎟 Quyidagilardan birini tanlang:", reply_markup=promo_kb())
    if o and o["status"] == "receipt":
        return await m.answer("🧾 To'lov <b>chekini</b> rasm qilib yuboring. Bekor qilish: /cancel")
    if o and o["status"] == "videos":
        return await m.answer("🎬 Videolaringizni yuboring. Bekor qilish: /cancel")
    await m.answer("Buyurtma berish uchun /start ni bosing 👇")


@r.error()
async def on_error(event: ErrorEvent):
    log.exception("Xatolik: %s", event.exception)
    return True


# ----------------------------------------------------------------------------
async def main():
    global DB, BOT_ID
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN o'rnatilmagan!")
    if not ADMIN_IDS:
        log.warning("ADMIN_IDS bo'sh — admin panel ishlamaydi!")
    if not CHANNEL_ID:
        log.warning("CHANNEL_ID bo'sh — buyurtmalar kanalga tushmaydi!")
    os.makedirs(DATA_DIR, exist_ok=True)
    DB = await aiosqlite.connect(os.path.join(DATA_DIR, "bot.db"))
    DB.row_factory = aiosqlite.Row
    await DB.execute("PRAGMA journal_mode=WAL")
    await DB.executescript(SCHEMA)
    # eski bazaga yangi ustunlar (promokod)
    for col, typ in (("promo_code", "TEXT"), ("promo_percent", "INTEGER")):
        try:
            await DB.execute(f"ALTER TABLE orders ADD COLUMN {col} {typ}")
        except Exception:
            pass
    await DB.commit()

    me = await bot.get_me()
    BOT_ID = me.id
    log.info("Bot ishga tushdi: @%s", me.username)

    await bot.set_my_commands([BotCommand(command="start", description="Boshlash")])
    for a in ADMIN_IDS:
        try:
            await bot.set_my_commands(
                [
                    BotCommand(command="start", description="Boshlash"),
                    BotCommand(command="admin", description="Admin panel"),
                    BotCommand(command="cancel", description="Bekor qilish"),
                ],
                scope=BotCommandScopeChat(chat_id=a),
            )
        except Exception as e:
            log.warning("admin commands %s: %s", a, e)

    dp = Dispatcher()
    dp.message.outer_middleware(Gate())
    dp.callback_query.outer_middleware(Gate())
    dp.include_router(r)
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
