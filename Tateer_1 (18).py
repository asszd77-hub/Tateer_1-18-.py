# -*- coding: utf-8 -*-
# ملف تشغيل نهائي: يثبت المكتبات المطلوبة تلقائياً عند غيابها
import sys as _sys
import subprocess as _subprocess
import importlib.util as _importlib_util

_REQUIRED_PACKAGES = {
    "telebot": "pyTelegramBotAPI",
    "aiohttp": "aiohttp",
    "pytz": "pytz",
}
for _module, _package in _REQUIRED_PACKAGES.items():
    if _importlib_util.find_spec(_module) is None:
        print(f"[SETUP] جاري تثبيت {_package}...", flush=True)
        _subprocess.check_call([_sys.executable, "-m", "pip", "install", _package])

import os
import sys
import asyncio
import aiohttp
import json
import random
import telebot
from telebot import types
from datetime import datetime, timedelta
import pytz
import time
import logging
import traceback
import uuid
from threading import Thread

# ====================================================================
# 1. الإعدادات والبيانات
# ====================================================================

BOT_TOKEN = "8918540263:AAFtZKNYqVAgcdY0HEVmyrZPhym3_NJKe2E"
ADMIN_ID = 1906886647 
CHANNEL_USERNAME = "@dollar7788" 
CHANNEL_URL = "https://t.me/dollar7788"
EGYPT_TZ = pytz.timezone("Africa/Cairo")

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot_errors.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("tateer_bot")

USERS_FILE = "bot_users.json"
CONFIG_FILE = "bot_config.json"
PENDING_REQUESTS_FILE = "pending_requests.json"

SUBSCRIPTION_PLANS = {
    "1": {"name": "اشتراك يوم", "price": 15, "days": 1},
    "2": {"name": "اشتراك 10 أيام", "price": 80, "days": 10},
    "3": {"name": "اشتراك شهر", "price": 150, "days": 30},
}

def load_data():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return {}
    return {}

def save_data(data):
    with open(USERS_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

def load_pending_requests():
    if os.path.exists(PENDING_REQUESTS_FILE):
        try:
            with open(PENDING_REQUESTS_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return []
    return []

def save_pending_requests(requests):
    with open(PENDING_REQUESTS_FILE, "w", encoding="utf-8") as f: json.dump(requests, f, ensure_ascii=False, indent=2)

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: pass
    return {"is_free": False, "total_ops": 0}

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f: json.dump(config, f, ensure_ascii=False, indent=2)

USERS = load_data()
CONFIG = load_config()
CONFIG.setdefault("is_free", False)
CONFIG.setdefault("total_ops", 0)
PENDING_REQUESTS = load_pending_requests()
bot = telebot.TeleBot(BOT_TOKEN)
ACTIVE_OPERATIONS = {}


def safe_edit_message(text, chat_id, message_id, **kwargs):
    """تحديث واجهة العملية بأمان؛ فشل Telegram لا يقتل العملية نفسها."""
    try:
        return bot.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            **kwargs
        )
    except Exception as exc:
        logger.warning("OP UI UPDATE FAILED | chat=%s | error=%s", chat_id, exc)
        return None


def safe_send_message(chat_id, text, **kwargs):
    try:
        return bot.send_message(chat_id, text, **kwargs)
    except Exception as exc:
        logger.warning("OP MESSAGE FAILED | chat=%s | error=%s", chat_id, exc)
        return None


def record_operation_result(user_id, op_type, success):
    """يحفظ نتيجة العملية منفصلة لكل مستخدم ونوع عملية."""
    uid = str(user_id)
    user = USERS.setdefault(uid, {})
    stats = user.setdefault("stats", {
        "total": 0, "success": 0, "failed": 0,
        "hold_success": 0, "hold_failed": 0,
        "auto_success": 0, "auto_failed": 0
    })
    for key in ("total", "success", "failed", "hold_success", "hold_failed", "auto_success", "auto_failed"):
        stats.setdefault(key, 0)
    kind = "hold" if op_type == "⭕تعليق دعوتين" else "auto"
    stats["total"] += 1
    stats["success" if success else "failed"] += 1
    stats[f"{kind}_{'success' if success else 'failed'}"] += 1
    save_data(USERS)


def user_stats_text():
    if not USERS:
        return "📊 لا يوجد مستخدمون مسجلون."
    rows = ["📊 إحصائيات المستخدمين", "━━━━━━━━━━━━━━━━━━"]
    for uid, user in USERS.items():
        stats = user.get("stats", {})
        name = user.get("first_name") or "بدون اسم"
        username = f"@{user.get('username')}" if user.get("username") else "بدون يوزر"
        rows.append(
            f"👤 {name} | {username}\n"
            f"🆔 ID: {uid}\n"
            f"📌 إجمالي العمليات: {stats.get('total', 0)}\n"
            f"✅ الناجحة: {stats.get('success', 0)} | ❌ الفاشلة: {stats.get('failed', 0)}\n"
            f"⭕ تعليق دعوتين — نجاح: {stats.get('hold_success', 0)} | فشل: {stats.get('hold_failed', 0)}\n"
            f"✅ قبول تلقائي — نجاح: {stats.get('auto_success', 0)} | فشل: {stats.get('auto_failed', 0)}\n"
            "──────────────────"
        )
    return "\n".join(rows)

# ====================================================================
# 2. التحقق والاشتراك
# ====================================================================

def check_channel_sub(user_id):
    if user_id == ADMIN_ID: return True
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ["member", "administrator", "creator"]: return True
    except: pass
    return False

def subscription_required(func):
    def wrapper(message):
        if not check_channel_sub(message.from_user.id):
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📢 انضم للقناة من هنا", url=CHANNEL_URL))
            markup.add(types.InlineKeyboardButton("✅ تم الانضمام", callback_data="check_sub"))
            bot.send_message(message.chat.id, f"⚠️ يجب عليك الانضمام لقناة البوت أولاً لاستخدامه!\nرابط القناة: {CHANNEL_URL}", reply_markup=markup)
            return
        return func(message)
    return wrapper

def get_cancel_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🛑 إلغاء العملية")
    return markup

def get_operation_control_keyboard(user_id):
    """لوحة تشغيل فيها زر إلغاء منفصل لكل عملية نشطة للمستخدم."""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🚀 بدء عملية جديدة")
    active = sorted(
        (
            (operation_id, operation)
            for operation_id, operation in ACTIVE_OPERATIONS.items()
            if operation.get("user_id") == user_id
        ),
        key=lambda item: item[1].get("started_at", "")
    )
    for index, _ in enumerate(active, 1):
        markup.add(f"🛑 إلغاء عملية {index}")
    return markup

def get_operation_cancel_keyboard(operation_id):
    """زر إلغاء مرتبط بعملية واحدة فقط ويظهر أسفل رسالة حالتها."""
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(
        "🛑 إلغاء العملية", callback_data=f"cancel_op:{operation_id}"
    ))
    return markup


def is_paid_user(user_id):
    if user_id == ADMIN_ID or CONFIG["is_free"]: return True
    user = USERS.get(str(user_id))
    if not user or "expire_date" not in user: return False
    expire_date = datetime.fromisoformat(user["expire_date"])
    return datetime.now(EGYPT_TZ) < expire_date

# ====================================================================
# 3. منطق Tateer Original King V4 (أقصى سرعة تزامن)
# ====================================================================

CLIENT_SECRET = "95fd95fb-7489-4958-8ae6-d31a525cd20a"
CLIENT_ID = "ana-vodafone-app"

def get_headers(msisdn, is_web=True):
    # التأكد من استخدام الرقم بالتنسيق المطلوب في الـ headers
    clean_msisdn = msisdn if msisdn.startswith("0") else "0" + msisdn.replace("201", "01").replace("20", "")
    if is_web:
        return {"msisdn": clean_msisdn, "Accept": "application/json", "Content-Type": "application/json; charset=UTF-8", "User-Agent": "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0", "Origin": "https://web.vodafone.com.eg", "Referer": "https://web.vodafone.com.eg/spa/familySharing", "clientId": "WebsiteConsumer"}
    return {"msisdn": clean_msisdn, "Accept": "application/json", "Content-Type": "application/json; charset=UTF-8", "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1", "Origin": "https://mobile.vodafone.com.eg", "Referer": "https://mobile.vodafone.com.eg/spa/familySharing", "clientId": "AnaVodafoneAndroid"}

async def login_async(session, phone, password):
    url = "https://mobile.vodafone.com.eg/auth/realms/vf-realm/protocol/openid-connect/token"
    payload = {"grant_type": "password", "username": phone, "password": password, "client_secret": CLIENT_SECRET, "client_id": CLIENT_ID}
    headers = {"User-Agent": "okhttp/4.12.0", "clientId": "AnaVodafoneAndroid"}
    last_error = "لم يتم الاتصال بالسيرفر"
    for attempt in range(3):
        try:
            async with session.post(url, data=payload, headers=headers, timeout=25) as response:
                body = await response.text()
                if response.status == 200:
                    data = json.loads(body)
                    token = data.get("access_token")
                    if token:
                        return token, None  # ✅ الإصلاح: دايمًا tuple
                    last_error = "✅ الاتصال نجح لكن السيرفر لم يُرسل token — ربما تغير API فودافون"
                elif response.status == 401:
                    # محاولة استخراج رسالة السيرفر
                    try:
                        err_data = json.loads(body)
                        srv_msg = err_data.get("error_description") or err_data.get("error") or body[:120]
                    except Exception:
                        srv_msg = body[:120]
                    last_error = f"❌ رقم أو باسورد غلط (401)\n📋 سيرفر: {srv_msg}"
                    break
                elif response.status == 400:
                    try:
                        err_data = json.loads(body)
                        srv_msg = err_data.get("error_description") or err_data.get("error") or body[:120]
                    except Exception:
                        srv_msg = body[:120]
                    last_error = f"❌ بيانات ناقصة أو خاطئة (400)\n📋 سيرفر: {srv_msg}"
                    break
                elif response.status == 403:
                    last_error = f"🚫 محظور من السيرفر (403) — قد يكون الحساب موقوف"
                    break
                elif response.status == 429:
                    last_error = f"⏳ كثرة المحاولات (429 Rate Limit) — انتظر وحاول لاحقاً"
                    break
                elif response.status == 500:
                    last_error = f"🔴 خطأ في سيرفر فودافون (500) — المشكلة من جهتهم"
                elif response.status == 503:
                    last_error = f"🔴 سيرفر فودافون غير متاح حالياً (503) — جرب لاحقاً"
                else:
                    last_error = f"⚠️ رد غير متوقع (status {response.status})\n📋 {body[:150]}"
        except asyncio.TimeoutError:
            last_error = f"⏱ انتهت مهلة الاتصال (25 ثانية) — السيرفر لم يرد"
            print(f"[LOGIN] Timeout محاولة {attempt+1} | رقم: {phone}")
        except aiohttp.ClientConnectorError as e:
            last_error = f"🌐 فشل الاتصال بالإنترنت: {str(e)}"
            print(f"[LOGIN] Connection Error | رقم: {phone} | {e}")
        except Exception as e:
            last_error = f"خطأ غير متوقع: {str(e)}"
            print(f"[LOGIN] Error محاولة {attempt+1} | رقم: {phone} | {e}")
        if attempt < 2:
            await asyncio.sleep(1.5)
    print(f"[LOGIN] فشل نهائي | رقم: {phone} | السبب: {last_error}")
    return None, last_error

async def invite_send_v4(session, token, owner, member, quota, is_web=True):
    url = "https://web.vodafone.com.eg/services/dxl/cg/customerGroupAPI/customerGroup" if is_web else "https://mobile.vodafone.com.eg/services/dxl/cg/customerGroupAPI/customerGroup"
    payload = {"name": "FlexFamily", "type": "SendInvitation", "category": [{"value": "523", "listHierarchyId": "PackageID"}, {"value": "47", "listHierarchyId": "TemplateID"}, {"value": "523", "listHierarchyId": "TierID"}, {"value": "percentage", "listHierarchyId": "familybehavior"}], "parts": {"member": [{"id": [{"value": owner, "schemeName": "MSISDN"}], "type": "Owner"}, {"id": [{"value": member, "schemeName": "MSISDN"}], "type": "Member"}], "characteristicsValue": {"characteristicsValue": [{"characteristicName": "quotaDist1", "value": str(quota), "type": "percentage"}]}}}
    headers = get_headers(owner, is_web)
    headers["Authorization"] = f"Bearer {token}"
    source = "🌐web" if is_web else "📱mob"
    try:
        async with session.post(url, json=payload, headers=headers, timeout=30) as r:
            text = await r.text()
            if r.status in [200, 201, 204]:
                return True, f"{source} ✅ ({r.status})"
            # استخراج رسالة السيرفر بشكل واضح
            try:
                err_data = json.loads(text)
                srv_msg = (err_data.get("message") or err_data.get("error_description")
                           or err_data.get("error") or err_data.get("description") or text[:200])
            except Exception:
                srv_msg = text[:200]
            # ترجمة أكواد الأخطاء الشائعة
            if r.status == 401:
                reason = f"{source} 🔑 Token منتهي أو غير صالح (401)"
            elif r.status == 403:
                reason = f"{source} 🚫 مرفوض (403) — الرقم محظور أو ليس عليه خطة مناسبة"
            elif r.status == 404:
                reason = f"{source} 🔍 الخدمة غير موجودة (404) — قد يكون الـ API تغير"
            elif r.status == 409:
                reason = f"{source} 🔄 دعوة موجودة مسبقاً (409) — يجب الإلغاء أولاً"
            elif r.status == 422:
                reason = f"{source} ⚠️ بيانات غير مقبولة (422)"
            elif r.status == 429:
                reason = f"{source} ⏳ Rate Limit (429) — فودافون قفلت الطلبات مؤقتاً"
            elif r.status == 500:
                reason = f"{source} 🔴 خطأ سيرفر فودافون (500)"
            elif r.status == 503:
                reason = f"{source} 🔴 السيرفر غير متاح (503)"
            else:
                reason = f"{source} ❓ status {r.status}"
            return False, f"{reason}\n📋 رد السيرفر: {srv_msg[:150]}"
    except asyncio.TimeoutError:
        return False, f"{source} ⏱ Timeout (30 ثانية) — السيرفر لم يرد"
    except aiohttp.ClientConnectorError as e:
        return False, f"{source} 🌐 خطأ اتصال: {str(e)}"
    except Exception as e:
        print(f"[INVITE ERROR] {source} {e}")
        return False, f"{source} خطأ: {str(e)}"

async def remove_member_async(session, token, owner, member):
    # التنسيق الدولي الصريح
    o_num = owner if owner.startswith("2") else "2" + owner
    m_num = member if member.startswith("2") else "2" + member
    
    # محاولة الحذف باستخدام الـ Payload التقليدي وإلغاء الدعوة
    payload_remove = {
        "category": [{"listHierarchyId": "TemplateID", "value": "47"}],
        "parts": {
            "member": [
                {"id": [{"schemeName": "MSISDN", "value": o_num}], "type": "Owner"},
                {"id": [{"schemeName": "MSISDN", "value": m_num}], "type": "Member"}
            ]
        },
        "type": "FamilyRemoveMember"
    }
    
    payload_cancel = {
        "category": [{"listHierarchyId": "TemplateID", "value": "47"}],
        "parts": {
            "member": [
                {"id": [{"schemeName": "MSISDN", "value": o_num}], "type": "Owner"},
                {"id": [{"schemeName": "MSISDN", "value": m_num}], "type": "Member"}
            ]
        },
        "type": "CancelInvitation"
    }
    
    headers = get_headers(owner, True)
    headers["Authorization"] = f"Bearer {token}"
    
    # قائمة الروابط والطرق لتجربتها بالترتيب
    attempts = [
        # 1. محاولة إلغاء الدعوة أولاً (POST) - هذا هو الحل لمشكلة الدعوة المعلقة
        ("POST", "https://web.vodafone.com.eg/services/dxl/cg/customerGroupAPI/customerGroup", payload_cancel),
        # 2. الرابط القياسي (DELETE)
        ("DELETE", "https://web.vodafone.com.eg/services/dxl/cg/customerGroupAPI/customerGroup", payload_remove),
        # 3. الرابط القياسي (POST)
        ("POST", "https://web.vodafone.com.eg/services/dxl/cg/customerGroupAPI/customerGroup", payload_remove),
        # 4. رابط إدارة العائلة البديل (DELETE)
        ("DELETE", "https://web.vodafone.com.eg/services/dxl/cg/manageFamilyAPI/manageFamily", payload_remove),
        # 5. رابط إدارة العائلة البديل (POST)
        ("POST", "https://web.vodafone.com.eg/services/dxl/cg/manageFamilyAPI/manageFamily", payload_remove)
    ]
    
    all_resps = []
    try:
        for method, url, p in attempts:
            try:
                if method == "DELETE":
                    async with session.delete(url, headers=headers, json=p, timeout=15) as r:
                        txt = await r.text()
                        if r.status in [200, 201, 204]: return True, txt
                        all_resps.append(f"{method} {url.split("/")[-1]}: {r.status}")
                else:
                    async with session.post(url, headers=headers, json=p, timeout=15) as r:
                        txt = await r.text()
                        if r.status in [200, 201, 204]: return True, txt
                        all_resps.append(f"{method} {url.split("/")[-1]}: {r.status}")
            except: continue
            
        return False, " | ".join(all_resps) if all_resps else "All routes failed"
                
    except Exception as e:
        return False, str(e)

async def accept_invitation_async(session, token, owner, member):
    url = "https://web.vodafone.com.eg/services/dxl/cg/customerGroupAPI/customerGroup"
    payload = {"category": [{"listHierarchyId": "TemplateID", "value": "47"}], "name": "FlexFamily", "parts": {"member": [{"id": [{"schemeName": "MSISDN", "value": owner}], "type": "Owner"}, {"id": [{"schemeName": "MSISDN", "value": member}], "type": "Member"}]}, "type": "AcceptInvitation"}
    headers = get_headers(member, True); headers["Authorization"] = f"Bearer {token}"
    try:
        async with session.patch(url, headers=headers, json=payload, timeout=20) as r: 
            return r.status in [200, 201, 204]
    except: return False

# ====================================================================
# 4. تدفق العملية
# ====================================================================

def get_main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🚀 بدء عملية جديدة")
    markup.add("👤 حسابي", "💳 تجديد الاشتراك")
    if user_id == ADMIN_ID: markup.add("⚙️ لوحة الإدارة")
    return markup

@bot.message_handler(func=lambda m: m.text == "🛑 إلغاء العملية" or (m.text or "").startswith("🛑 إلغاء عملية "))
def cancel_global(message):
    user_id = message.from_user.id
    user_operations = [
        (operation_id, operation)
        for operation_id, operation in ACTIVE_OPERATIONS.items()
        if operation.get("user_id") == user_id
    ]
    if user_operations:
        user_operations.sort(key=lambda item: item[1].get("started_at", ""))
        selected_index = None
        if (message.text or "").startswith("🛑 إلغاء عملية "):
            try:
                selected_index = int(message.text.rsplit(" ", 1)[1]) - 1
            except (ValueError, IndexError):
                selected_index = None
        if selected_index is not None and 0 <= selected_index < len(user_operations):
            operation_id, _ = user_operations[selected_index]
        else:
            operation_id, _ = user_operations[-1]
        ACTIVE_OPERATIONS.pop(operation_id, None)
    bot.clear_step_handler_by_chat_id(message.chat.id)
    remaining = any(
        operation.get("user_id") == user_id
        for operation in ACTIVE_OPERATIONS.values()
    )
    bot.send_message(
        message.chat.id,
        "🛑 تم إلغاء العملية المحددة." if user_operations else "ℹ️ لا توجد عملية نشطة.",
        reply_markup=get_operation_control_keyboard(user_id) if remaining else get_main_keyboard(user_id)
    )

@bot.message_handler(commands=["start"])
def start(message):
    user_id = str(message.from_user.id)
    is_new = user_id not in USERS
    if is_new:
        USERS[user_id] = {
            "joined": datetime.now(EGYPT_TZ).isoformat(),
            "expire_date": datetime.now(EGYPT_TZ).isoformat(),
            "first_name": message.from_user.first_name or "",
            "username": message.from_user.username or ""
        }
        save_data(USERS)
        try:
            uname = f"@{message.from_user.username}" if message.from_user.username else "بدون يوزر"
            fname = message.from_user.first_name or "بدون اسم"
            bot.send_message(
                ADMIN_ID,
                f"🔔 *مستخدم جديد انضم للبوت!*\n\n"
                f"👤 الاسم: {fname}\n"
                f"🔗 اليوزر: {uname}\n"
                f"🆔 ID: `{user_id}`\n"
                f"📅 التاريخ: {datetime.now(EGYPT_TZ).strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"👥 إجمالي المستخدمين: {len(USERS)}",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"[NEW USER NOTIFY ERROR] {e}")

    bot.send_message(
        message.chat.id,
        f"👋 *أهلاً بك في Tateer Original King!*\n\n"
        f"📢 قناة البوت: {CHANNEL_URL}",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@bot.message_handler(func=lambda m: m.text == "🚀 بدء عملية جديدة")
@subscription_required
def start_op(message):
    if not is_paid_user(message.from_user.id):
        bot.send_message(message.chat.id, "⚠️ عذراً، يجب أن يكون لديك اشتراك مفعل لاستخدام البوت.")
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("✅قبول تلقائي", "⭕تعليق دعوتين")
    markup.add("🛑 إلغاء العملية")
    bot.send_message(message.chat.id, "🔄 اختر نوع العملية أولاً:", reply_markup=markup)
    bot.register_next_step_handler(message, get_owner_num)

def get_owner_num(message):
    if message.text == "🛑 إلغاء العملية": return cancel_global(message)
    op_type = message.text.strip()
    if op_type not in ["✅قبول تلقائي", "⭕تعليق دعوتين"]:
        bot.send_message(message.chat.id, "❌ اختيار غير صحيح.")
        return
    bot.send_message(message.chat.id, "📱 أدخل رقم الأونر (المالك):", reply_markup=get_cancel_keyboard())
    bot.register_next_step_handler(message, get_owner_pass, op_type)

def get_owner_pass(message, op_type):
    if message.text == "🛑 إلغاء العملية": return cancel_global(message)
    owner_num = message.text.strip()
    bot.send_message(message.chat.id, "🔒 أدخل باسورد الأونر:", reply_markup=get_cancel_keyboard())
    bot.register_next_step_handler(message, get_member_num, op_type, owner_num)

def get_member_num(message, op_type, owner_num):
    if message.text == "🛑 إلغاء العملية": return cancel_global(message)
    owner_pass = message.text.strip()
    bot.send_message(message.chat.id, "👥 أدخل رقم الفرد:", reply_markup=get_cancel_keyboard())
    bot.register_next_step_handler(message, get_member_pass, op_type, owner_num, owner_pass)

def get_member_pass(message, op_type, owner_num, owner_pass):
    if message.text == "🛑 إلغاء العملية": return cancel_global(message)
    member_num = message.text.strip()
    bot.send_message(message.chat.id, "🔑 أدخل باسورد الفرد:", reply_markup=get_cancel_keyboard())
    bot.register_next_step_handler(message, get_quota, op_type, owner_num, owner_pass, member_num)

def get_quota(message, op_type, owner_num, owner_pass, member_num):
    if message.text == "🛑 إلغاء العملية": return cancel_global(message)
    member_pass = message.text.strip()
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("10", "20", "40")
    markup.add("🛑 إلغاء العملية")
    bot.send_message(message.chat.id, "📊 اختر النسبة (10, 20, 40):", reply_markup=markup)
    bot.register_next_step_handler(message, run_operation, op_type, owner_num, owner_pass, member_num, member_pass)

def run_operation(message, op_type, owner_num, owner_pass, member_num, member_pass):
    if message.text == "🛑 إلغاء العملية": return cancel_global(message)
    quota = message.text.strip()
    operation_id = uuid.uuid4().hex[:12]
    ACTIVE_OPERATIONS[operation_id] = {
        "user_id": message.from_user.id,
        "chat_id": message.chat.id,
        "type": op_type,
        "started_at": datetime.now(EGYPT_TZ).isoformat()
    }
    Thread(target=lambda: asyncio.run(run_op_async(operation_id, message.chat.id, message.from_user.id, owner_num, owner_pass, member_num, member_pass, quota, op_type))).start()

# ====================================================================
# 5. تنفيذ العملية (المنطق المثالي والمطلوب حرفياً)
# ====================================================================

async def _run_op_async(operation_id, chat_id, user_id, owner_num, owner_pass, member_num, member_pass, quota, op_type):
    cancel_markup = get_operation_control_keyboard(user_id)
    msg = bot.send_message(
        chat_id,
        "⏳ جاري البدء بأقصى سرعة إرسال...\n🔑 جاري تسجيل الدخول..."
    )
    bot.send_message(chat_id, "🛑 لإلغاء العملية الحالية اضغط الزر التالي:", reply_markup=cancel_markup)
    
    # استخدام TCPConnector لسرعة قصوى مع تعطيل الـ SSL Verification لتقليل وقت الاستجابة
    connector = aiohttp.TCPConnector(limit=20, ttl_dns_cache=300, ssl=False, limit_per_host=4)
    async with aiohttp.ClientSession(connector=connector) as session:
        login_tasks = [
            asyncio.create_task(login_async(session, owner_num, owner_pass)),
            asyncio.create_task(login_async(session, member_num, member_pass)),
        ]
        login_started = time.monotonic()
        while not all(task.done() for task in login_tasks):
            await asyncio.sleep(2)
            if operation_id not in ACTIVE_OPERATIONS:
                for task in login_tasks:
                    task.cancel()
                return
            elapsed = int(time.monotonic() - login_started)
            safe_edit_message(
                f"⏳ جاري البدء بأقصى سرعة إرسال...\n"
                f"🔑 جاري تسجيل الدخول... ({elapsed} ثانية)",
                chat_id,
                msg.message_id,
                            )
        results_login = await asyncio.gather(*login_tasks)

        # login_async ترجع token مباشرة لو نجحت، أو (None, error) لو فشلت
        def parse_login(res):
            if isinstance(res, tuple):
                return res[0], res[1]
            return res, None

        o_token, o_err = parse_login(results_login[0])
        m_token, m_err = parse_login(results_login[1])

        if not o_token or not m_token:
            o_status = "✅ نجح" if o_token else f"❌ فشل\n    ↳ {o_err or 'خطأ غير معروف'}"
            m_status = "✅ نجح" if m_token else f"❌ فشل\n    ↳ {m_err or 'خطأ غير معروف'}"
            fail_msg = (
                "❌ *فشل تسجيل الدخول!*\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                f"👑 *الأونر* ({owner_num}):\n{o_status}\n\n"
                f"👤 *الفرد* ({member_num}):\n{m_status}\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                "💡 *تحقق من:*\n"
                "• صحة الأرقام والباسوردات\n"
                "• أن الحساب غير موقوف\n"
                "• اتصال الإنترنت بالسيرفر"
            )
            safe_edit_message(fail_msg, chat_id, msg.message_id, parse_mode="Markdown")
            try:
                bot.send_message(
                    ADMIN_ID,
                    f"⚠️ *فشل تسجيل دخول*\n"
                    f"👤 مستخدم: `{user_id}`\n"
                    f"👑 أونر: `{owner_num}`\n↳ {o_err or 'OK'}\n"
                    f"👤 فرد: `{member_num}`\n↳ {m_err or 'OK'}",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
            record_operation_result(user_id, op_type, False)
            ACTIVE_OPERATIONS.pop(operation_id, None)
            return

        safe_edit_message("✅ تم تسجيل الدخول بنجاح! جاري بدء العملية...", chat_id, msg.message_id)

        success_count = 0
        last_resp = ""
        all_fail_reasons = []  # لتجميع أسباب الفشل عبر المحاولات

        for i in range(1, 11):
            if operation_id not in ACTIVE_OPERATIONS:
                safe_edit_message("🛑 تم إلغاء العملية.", chat_id, msg.message_id); return

            safe_edit_message(
                f"🚀 *ضرب رباعي — محاولة {i}/10*\n⏳ جاري الإرسال...",
                chat_id, msg.message_id,
                                                parse_mode="Markdown"
            )

            # إرسال متدرج بدل إرسال كل الطلبات في نفس اللحظة
            async def send_with_delay(is_web, delay):
                await asyncio.sleep(delay)
                return await invite_send_v4(session, o_token, owner_num, member_num, quota, is_web)

            tasks = [
                send_with_delay(True,  0.0),   # web  فوري
                send_with_delay(False, 0.3),   # mob  بعد 300ms
                send_with_delay(True,  0.6),   # web  بعد 600ms
                send_with_delay(False, 0.9),   # mob  بعد 900ms
            ]
            results = await asyncio.gather(*tasks)

            if operation_id not in ACTIVE_OPERATIONS:
                return

            success_count = sum(1 for s, _ in results if s)
            fail_details = [detail for s, detail in results if not s]

            if success_count >= 2:
                break

            if success_count == 1:
                safe_edit_message(
                    f"⚠️ *نجحت دعوة واحدة فقط (محاولة {i})*\n"
                    f"⏳ انتظار 30 ثانية قبل الإلغاء وإعادة المحاولة...",
                    chat_id, msg.message_id,
                                                            parse_mode="Markdown"
                )
                await asyncio.sleep(30)
                if operation_id not in ACTIVE_OPERATIONS: return

                safe_edit_message("🔄 جاري إلغاء الدعوة الواحدة...", chat_id, msg.message_id)
                success_cancel, cancel_resp = await remove_member_async(session, o_token, owner_num, member_num)
                if success_cancel:
                    safe_edit_message(
                        f"✅ تم إلغاء الدعوة. إعادة المحاولة خلال 5 ثوانٍ...",
                        chat_id, msg.message_id
                    )
                    await asyncio.sleep(5)
                else:
                    safe_edit_message(
                        f"❌ *فشل إلغاء الدعوة الواحدة*\n"
                        f"📋 السبب: {cancel_resp[:150]}\n"
                        f"🛑 تم إيقاف العملية لضمان السلامة.",
                        chat_id, msg.message_id,
                                                parse_mode="Markdown"
                    )
                    record_operation_result(user_id, op_type, False)
                    ACTIVE_OPERATIONS.pop(operation_id, None)
                    return
            else:
                # لم تنجح أي دعوة — نعرض أسباب الفشل بالتفصيل
                last_resp = fail_details[0] if fail_details else "لا يوجد رد"
                all_fail_reasons = fail_details

                # كشف Rate Limit في أي من الردود
                combined = " ".join(fail_details).lower()
                is_rate_limit = "rate limit" in combined or "429" in combined or "⏳" in combined

                fail_summary = "\n".join(f"  {d}" for d in fail_details[:4]) if fail_details else "لا يوجد تفاصيل"
                status_msg = (
                    f"❌ *فشل المحاولة {i}/10*\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"📊 نجح: {success_count}/4 طلبات\n"
                    f"📋 *تفاصيل الفشل:*\n{fail_summary}\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                )
                if is_rate_limit:
                    wait = 20 if i <= 3 else 35
                    status_msg += f"⏳ Rate Limit مكتشف — انتظار {wait} ثانية تلقائياً..."
                    safe_edit_message(status_msg, chat_id, msg.message_id, parse_mode="Markdown")
                    await asyncio.sleep(wait)
                else:
                    status_msg += f"🔄 إعادة المحاولة خلال 4 ثوانٍ..."
                    safe_edit_message(status_msg, chat_id, msg.message_id, parse_mode="Markdown")
                    await asyncio.sleep(4)

        if success_count < 2:
            fail_summary = "\n".join(f"• {d}" for d in all_fail_reasons[:4]) if all_fail_reasons else last_resp[:200]
            final_fail_msg = (
                f"❌ *فشل بعد 10 محاولات*\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"📋 *آخر أسباب الفشل:*\n{fail_summary}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"💡 *المقترح:* تحقق من الأسباب أعلاه وأرسلها للدعم."
            )
            safe_edit_message(final_fail_msg, chat_id, msg.message_id, parse_mode="Markdown")
            try:
                bot.send_message(
                    ADMIN_ID,
                    f"❌ *فشل عملية كاملة*\n"
                    f"👤 مستخدم: `{user_id}`\n"
                    f"👑 أونر: `{owner_num}`\n"
                    f"👤 فرد: `{member_num}`\n"
                    f"📋 السبب:\n{fail_summary}",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
            record_operation_result(user_id, op_type, False)
            ACTIVE_OPERATIONS.pop(operation_id, None); return

        if op_type == "⭕تعليق دعوتين":
            safe_edit_message(
                f"✅ *نجح التعليق!* 🎯\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"📊 دعوات ناجحة: {success_count}/4\n"
                f"👑 الأونر: `{owner_num}`\n"
                f"👤 الفرد: `{member_num}`",
                chat_id, msg.message_id,
                                                parse_mode="Markdown"
            )
            CONFIG["total_ops"] += 1; save_config(CONFIG)
            record_operation_result(user_id, op_type, True)
            ACTIVE_OPERATIONS.pop(operation_id, None); return

        safe_edit_message(
            f"✅ *تم إرسال {success_count} دعوات بنجاح!*\n"
            f"⏳ انتظار 5 دقائق قبل القبول التلقائي...\n"
            f"_(اضغط إلغاء إذا أردت إيقاف العملية)_",
            chat_id, msg.message_id,
                                    parse_mode="Markdown"
        )
        await asyncio.sleep(300)

        if operation_id not in ACTIVE_OPERATIONS:
            record_operation_result(user_id, op_type, False)
            return

        safe_edit_message("🔄 جاري القبول التلقائي...", chat_id, msg.message_id)
        accept_ok = await accept_invitation_async(session, m_token, owner_num, member_num)
        if accept_ok:
            safe_edit_message(
                f"🎉 *تمت العملية بنجاح كامل!*\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"✅ الإرسال: {success_count}/4 دعوات\n"
                f"✅ القبول: تم تلقائياً\n"
                f"👑 الأونر: `{owner_num}`\n"
                f"👤 الفرد: `{member_num}`\n"
                f"📊 النسبة: {quota}%",
                chat_id, msg.message_id,
                                                parse_mode="Markdown"
            )
            CONFIG["total_ops"] += 1; save_config(CONFIG)
            record_operation_result(user_id, op_type, True)
        else:
            record_operation_result(user_id, op_type, False)
            safe_edit_message(
                f"⚠️ *تم الإرسال لكن فشل القبول التلقائي!*\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"✅ الإرسال: {success_count}/4 دعوات — نجح\n"
                f"❌ القبول: فشل\n\n"
                f"💡 *المقترح:* اقبل الدعوة يدوياً من تطبيق فودافون.",
                chat_id, msg.message_id,
                                                parse_mode="Markdown"
            )
            
    ACTIVE_OPERATIONS.pop(operation_id, None)


async def run_op_async(operation_id, chat_id, user_id, owner_num, owner_pass, member_num, member_pass, quota, op_type):
    """مشغل مستقل لكل مستخدم؛ أخطاء Telegram لا توقف polling أو عمليات الآخرين."""
    try:
        await _run_op_async(operation_id, chat_id, user_id, owner_num, owner_pass, member_num, member_pass, quota, op_type)
    except Exception as exc:
        logger.exception("OPERATION CRASH | user=%s | type=%s", user_id, op_type)
        ACTIVE_OPERATIONS.pop(operation_id, None)
        safe_send_message(chat_id, "❌ حدث خطأ في هذه العملية فقط. تم تسجيل الخطأ، ويمكنك إعادة المحاولة.")

# ====================================================================
# 6. نظام الاشتراكات الجديد — مبسط من الصفر
# ====================================================================

PAYMENT_NUMBER = "01026292411"


def subscription_plans_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, plan in SUBSCRIPTION_PLANS.items():
        markup.add(types.InlineKeyboardButton(
            f"{plan['name']} — {plan['price']} جنيه",
            callback_data=f"new_sub:{key}"
        ))
    return markup


def admin_keyboard():
    mode = "مجاني" if CONFIG.get("is_free", False) else "مدفوع"
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    markup.add(f"تغيير الوضع الحالي: {mode}")
    markup.add(f"طلبات التفعيل ({len(PENDING_REQUESTS)})")
    markup.add("إضافة اشتراك يدوي")
    markup.add("الإحصائيات")
    markup.add("إحصائيات المستخدمين")
    markup.add("👥 بيانات المستخدمين")
    markup.add("📢 إذاعة للمستخدمين")
    markup.add("العودة للقائمة الرئيسية")
    return markup


def send_subscription_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("اشتراك يوم - 15 جنيه")
    markup.add("اشتراك 10 أيام - 80 جنيه")
    markup.add("اشتراك شهر - 150 جنيه")
    markup.add("🛑 إلغاء العملية")
    bot.send_message(
        message.chat.id,
        "💳 اختر مدة الاشتراك المطلوبة:",
        reply_markup=markup
    )


def save_request_and_notify_admin(message, plan_key, sender_number):
    request_id = f"{message.from_user.id}_{int(datetime.now().timestamp())}_{random.randint(100,999)}"
    request = {
        "id": request_id,
        "user_id": message.from_user.id,
        "username": message.from_user.username or "",
        "plan": plan_key,
        "sender_num": sender_number,
        "time": datetime.now(EGYPT_TZ).isoformat()
    }
    PENDING_REQUESTS.append(request)
    save_pending_requests(PENDING_REQUESTS)
    plan = SUBSCRIPTION_PLANS[plan_key]
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(f"✅ قبول الطلب {request_id}", f"❌ رفض الطلب {request_id}")
    bot.send_message(message.chat.id, "✅ تم تسجيل طلبك وإرساله للإدارة للمراجعة.")
    bot.send_message(
        ADMIN_ID,
        f"🔔 طلب تفعيل اشتراك جديد\n\n"
        f"👤 المستخدم: {message.from_user.id}\n"
        f"🔗 اليوزر: @{message.from_user.username or 'بدون يوزر'}\n"
        f"📱 رقم التحويل: {sender_number}\n"
        f"📦 الخطة: {plan['name']}\n"
        f"💰 المبلغ: {plan['price']} جنيه\n"
        f"🆔 الطلب: {request_id}",
        reply_markup=markup
    )


def receive_payment_number(message, plan_key):
    if message.text == "🛑 إلغاء العملية":
        return cancel_global(message)
    number = (message.text or "").strip()
    if len(number) < 5:
        prompt = bot.send_message(message.chat.id, "❌ اكتب رقم الهاتف الذي تم التحويل منه بشكل صحيح:", reply_markup=get_cancel_keyboard())
        bot.register_next_step_handler(prompt, receive_payment_number, plan_key)
        return
    save_request_and_notify_admin(message, plan_key, number)
    bot.send_message(message.chat.id, "📌 سيتم تفعيل الاشتراك بعد مراجعة التحويل من الإدارة.", reply_markup=get_main_keyboard(message.from_user.id))


def activate_request(message, request_id):
    global PENDING_REQUESTS
    request = next((r for r in PENDING_REQUESTS if str(r.get("id")) == str(request_id)), None)
    if not request:
        bot.send_message(message.chat.id, "⚠️ الطلب غير موجود أو تم التعامل معه من قبل.")
        return
    plan = SUBSCRIPTION_PLANS.get(str(request.get("plan")))
    if not plan:
        bot.send_message(message.chat.id, "❌ خطة الاشتراك غير موجودة.")
        return
    uid = str(request["user_id"])
    user = USERS.setdefault(uid, {"joined": datetime.now(EGYPT_TZ).isoformat()})
    now = datetime.now(EGYPT_TZ)
    try:
        old = datetime.fromisoformat(user.get("expire_date", ""))
        base = old if old > now else now
    except Exception:
        base = now
    user["subscription_plan"] = plan["name"]
    user["subscription_price"] = plan["price"]
    user["subscription_days"] = plan["days"]
    user["subscription_activated_at"] = now.isoformat()
    user["expire_date"] = (base + timedelta(days=plan["days"])).isoformat()
    save_data(USERS)
    PENDING_REQUESTS = [r for r in PENDING_REQUESTS if str(r.get("id")) != str(request_id)]
    save_pending_requests(PENDING_REQUESTS)
    bot.send_message(message.chat.id, f"✅ تم تفعيل {plan['name']} للمستخدم {uid}.")
    try:
        bot.send_message(int(uid), f"🎉 تم تفعيل اشتراكك: {plan['name']}\nينتهي في: {user['expire_date']}")
    except Exception as exc:
        print(f"[ACTIVATION NOTIFY ERROR] {exc}")


def reject_request(message, request_id):
    global PENDING_REQUESTS
    request = next((r for r in PENDING_REQUESTS if str(r.get("id")) == str(request_id)), None)
    if not request:
        bot.send_message(message.chat.id, "⚠️ الطلب غير موجود أو تم التعامل معه من قبل.")
        return
    PENDING_REQUESTS = [r for r in PENDING_REQUESTS if str(r.get("id")) != str(request_id)]
    save_pending_requests(PENDING_REQUESTS)
    bot.send_message(message.chat.id, f"❌ تم رفض طلب المستخدم {request['user_id']}.")
    try:
        bot.send_message(int(request["user_id"]), "❌ تم رفض طلب الاشتراك. تواصل مع الإدارة إذا كان هناك خطأ.")
    except Exception:
        pass


def show_pending(message):
    if not PENDING_REQUESTS:
        bot.send_message(message.chat.id, "📭 لا توجد طلبات تفعيل معلقة.")
        return
    for request in PENDING_REQUESTS:
        plan = SUBSCRIPTION_PLANS.get(str(request.get("plan")), {})
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(f"✅ قبول الطلب {request['id']}", f"❌ رفض الطلب {request['id']}")
        bot.send_message(
            message.chat.id,
            f"🆔 الطلب: {request['id']}\n👤 المستخدم: {request['user_id']}\n"
            f"📱 رقم التحويل: {request.get('sender_num', '')}\n📦 الخطة: {plan.get('name', 'غير معروفة')}",
            reply_markup=markup
        )


def add_manual_subscription(message):
    if message.text == "🛑 إلغاء العملية":
        return cancel_global(message)
    try:
        uid, days_text = (message.text or "").split()[:2]
        days = int(days_text)
        if days <= 0:
            raise ValueError
        user = USERS.setdefault(uid, {"joined": datetime.now(EGYPT_TZ).isoformat()})
        now = datetime.now(EGYPT_TZ)
        try:
            old = datetime.fromisoformat(user.get("expire_date", ""))
            base = old if old > now else now
        except Exception:
            base = now
        user["subscription_plan"] = "اشتراك يدوي"
        user["subscription_price"] = 0
        user["subscription_days"] = days
        user["subscription_activated_at"] = now.isoformat()
        user["expire_date"] = (base + timedelta(days=days)).isoformat()
        save_data(USERS)
        bot.send_message(message.chat.id, f"✅ تمت إضافة {days} يومًا للمستخدم {uid}.", reply_markup=admin_keyboard())
    except Exception:
        prompt = bot.send_message(message.chat.id, "❌ الصيغة الصحيحة: ID عدد_الأيام\nمثال: 123456789 30")
        bot.register_next_step_handler(prompt, add_manual_subscription)


def start_direct_subscription(message, plan_key):
    """مسار احتياطي للأزرار النصية القديمة أو Reply Keyboard."""
    plan = SUBSCRIPTION_PLANS.get(plan_key)
    if not plan:
        bot.send_message(message.chat.id, "❌ خطة الاشتراك غير موجودة.")
        return
    prompt = bot.send_message(
        message.chat.id,
        f"✅ اخترت: {plan['name']}\n💰 المطلوب: {plan['price']} جنيه\n\n"
        f"💳 حوّل المبلغ إلى: {PAYMENT_NUMBER}\n\n"
        "بعد التحويل أرسل رقم الهاتف الذي حوّلت منه.",
        reply_markup=get_cancel_keyboard()
    )
    bot.register_next_step_handler(prompt, receive_payment_number, plan_key)


# ====================================================================
# 7. الكولباك والرسائل الجديدة
# ====================================================================

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    print(
        f"[CALLBACK RECEIVED] data={getattr(call, 'data', None)} "
        f"user={getattr(getattr(call, 'from_user', None), 'id', None)}",
        flush=True
    )
    try:
        data = call.data or ""
        uid = call.from_user.id
        logger.info("CALLBACK received | user=%s | data=%s", uid, data)
        # دعم أزرار الرسائل القديمة التي أُرسلت قبل إعادة بناء النظام.
        if data.startswith("sub_plan_"):
            data = "new_sub:" + data.replace("sub_plan_", "", 1)
        elif data == "toggle_free":
            data = "new_admin:toggle"
        elif data == "view_pending_requests":
            data = "new_admin:pending"
        elif data == "add_sub":
            data = "new_admin:add"
        if data == "check_sub":
            if check_channel_sub(uid):
                bot.answer_callback_query(call.id, "✅ تم التحقق")
                start(call.message)
            else:
                bot.answer_callback_query(call.id, "❌ اشترك في القناة أولاً", show_alert=True)
            return
        if data == "cancel_op" or data.startswith("cancel_op:"):
            if data == "cancel_op":
                candidates = [
                    (op_id, op)
                    for op_id, op in ACTIVE_OPERATIONS.items()
                    if op.get("user_id") == uid
                ]
                operation_id = max(
                    candidates,
                    key=lambda item: item[1].get("started_at", "")
                )[0] if candidates else ""
            else:
                operation_id = data.split(":", 1)[1]
            print(
                f"[CANCEL DEBUG] user={uid} operation_id={operation_id} "
                f"active_ids={list(ACTIVE_OPERATIONS.keys())}",
                flush=True
            )
            bot.answer_callback_query(call.id, "⏳ جاري إلغاء العملية...", show_alert=False)
            operation = ACTIVE_OPERATIONS.get(operation_id)
            if operation is None:
                print("[CANCEL DEBUG] operation_not_found", flush=True)
                bot.send_message(call.message.chat.id, "ℹ️ العملية انتهت أو تم إلغاؤها.")
                return
            if operation.get("user_id") != uid:
                print(
                    f"[CANCEL DEBUG] owner_mismatch expected={operation.get('user_id')} actual={uid}",
                    flush=True
                )
                bot.send_message(call.message.chat.id, "❌ هذا الزر ليس لعمليتك.")
                return
            ACTIVE_OPERATIONS.pop(operation_id, None)
            print(
                f"[CANCEL DEBUG] removed={operation_id} "
                f"remaining={list(ACTIVE_OPERATIONS.keys())}",
                flush=True
            )
            safe_edit_message(
                "🛑 تم إلغاء العملية المحددة.",
                call.message.chat.id,
                call.message.message_id
            )
            bot.send_message(call.message.chat.id, "🏠 تم الرجوع للقائمة الرئيسية.", reply_markup=get_main_keyboard(uid))
            return
        if data.startswith("new_sub:"):
            key = data.split(":", 1)[1]
            plan = SUBSCRIPTION_PLANS.get(key)
            if not plan:
                bot.answer_callback_query(call.id, "❌ الخطة غير موجودة", show_alert=True)
                return
            bot.answer_callback_query(call.id, "✅ تم اختيار الخطة")
            prompt = bot.send_message(
                call.message.chat.id,
                f"✅ اخترت: {plan['name']}\n💰 المطلوب: {plan['price']} جنيه\n\n"
                f"💳 حوّل المبلغ إلى: {PAYMENT_NUMBER}\n\n"
                "بعد التحويل أرسل رقم الهاتف الذي حوّلت منه.",
                reply_markup=get_cancel_keyboard()
            )
            bot.register_next_step_handler(prompt, receive_payment_number, key)
            return
        if data.startswith("new_admin:") and uid == ADMIN_ID:
            action = data.split(":", 1)[1]
            bot.answer_callback_query(call.id, "✅ تم")
            if action == "toggle":
                CONFIG["is_free"] = not CONFIG.get("is_free", False)
                save_config(CONFIG)
                bot.send_message(call.message.chat.id, "✅ تم تغيير وضع البوت.", reply_markup=admin_keyboard())
            elif action == "pending":
                show_pending(call.message)
            elif action == "stats":
                bot.send_message(call.message.chat.id, f"📊 الإحصائيات\n👥 المستخدمون: {len(USERS)}\n✅ العمليات الناجحة: {CONFIG.get('total_ops', 0)}\n⏳ الطلبات المعلقة: {len(PENDING_REQUESTS)}\n🔐 الوضع: {'مجاني' if CONFIG.get('is_free') else 'مدفوع'}")
            elif action == "add":
                prompt = bot.send_message(call.message.chat.id, "أرسل ID المستخدم وعدد الأيام، مثال: 123456789 30", reply_markup=get_cancel_keyboard())
                bot.register_next_step_handler(prompt, add_manual_subscription)
            return
        if data.startswith("new_req:") and uid == ADMIN_ID:
            _, action, request_id = data.split(":", 2)
            bot.answer_callback_query(call.id, "✅ تم استلام القرار")
            if action == "approve":
                activate_request(call.message, request_id)
            elif action == "reject":
                reject_request(call.message, request_id)
            return
        bot.answer_callback_query(call.id, "ℹ️ هذا الزر غير متاح")
    except Exception as exc:
        logger.error("CALLBACK ERROR | data=%s | error=%s", getattr(call, "data", ""), exc)
        traceback.print_exc()
        try:
            bot.send_message(
                call.message.chat.id,
                f"❌ حدث خطأ أثناء تنفيذ الزر.\n\n"
                f"نوع الخطأ: {type(exc).__name__}\n"
                f"التفاصيل: {exc}"
            )
        except Exception:
            pass
        try:
            bot.answer_callback_query(call.id, "❌ حدث خطأ", show_alert=True)
        except Exception:
            pass


@bot.message_handler(func=lambda m: m.text == "⚙️ لوحة الإدارة" and m.from_user.id == ADMIN_ID)
def admin_panel(message):
    bot.send_message(message.chat.id, "🛠️ لوحة الإدارة الجديدة", reply_markup=admin_keyboard())


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and bool(m.text) and m.text.startswith("تغيير الوضع الحالي:"))
def admin_toggle_text(message):
    CONFIG["is_free"] = not CONFIG.get("is_free", False)
    save_config(CONFIG)
    bot.send_message(message.chat.id, "✅ تم تغيير وضع البوت.", reply_markup=admin_keyboard())


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and bool(m.text) and m.text.startswith("طلبات التفعيل"))
def admin_pending_text(message):
    show_pending(message)


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and bool(m.text) and m.text.startswith("✅ قبول الطلب "))
def admin_approve_text(message):
    request_id = message.text.replace("✅ قبول الطلب ", "", 1).strip()
    activate_request(message, request_id)


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and bool(m.text) and m.text.startswith("❌ رفض الطلب "))
def admin_reject_text(message):
    request_id = message.text.replace("❌ رفض الطلب ", "", 1).strip()
    reject_request(message, request_id)


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "إحصائيات المستخدمين")
def admin_user_stats_text(message):
    bot.send_message(message.chat.id, user_stats_text(), reply_markup=admin_keyboard())


def all_users_details_text():
    if not USERS:
        return ["📭 لا يوجد مستخدمون مسجلون."]
    blocks = []
    for uid, user in USERS.items():
        expire_text = user.get("expire_date")
        status = "لا يوجد اشتراك"
        remaining = 0
        if expire_text:
            try:
                expire = datetime.fromisoformat(expire_text)
                now = datetime.now(EGYPT_TZ)
                remaining = max(0, (expire - now).days)
                status = "✅ مفعل" if now < expire else "❌ منتهي"
            except Exception:
                status = "⚠️ تاريخ غير صحيح"
        username = f"@{user.get('username')}" if user.get("username") else "بدون يوزر"
        plan = user.get("subscription_plan", "غير محدد")
        price = user.get("subscription_price", "-")
        days = user.get("subscription_days", "-")
        activated = user.get("subscription_activated_at", "-")
        blocks.append(
            f"👤 {user.get('first_name') or 'بدون اسم'} | {username}\n"
            f"🆔 ID: {uid}\n"
            f"📦 الاشتراك: {plan}\n"
            f"💰 السعر: {price} جنيه | المدة: {days} يوم\n"
            f"📅 التفعيل: {activated}\n"
            f"⏳ الانتهاء: {expire_text or '-'}\n"
            f"📊 المتبقي: {remaining} يوم | الحالة: {status}"
        )
    chunks=[]
    current="📋 بيانات المستخدمين\n\n"
    for block in blocks:
        if len(current)+len(block)+3 > 3800:
            chunks.append(current)
            current=""
        current += block + "\n\n"
    if current.strip():
        chunks.append(current)
    return chunks


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "👥 بيانات المستخدمين")
def admin_user_details_text(message):
    for chunk in all_users_details_text():
        bot.send_message(message.chat.id, chunk, reply_markup=admin_keyboard())


def send_broadcast(message):
    if message.text == "🛑 إلغاء العملية":
        return cancel_global(message)
    text = (message.text or "").strip()
    if not text:
        prompt = bot.send_message(message.chat.id, "❌ الرسالة فارغة. أرسل نص الإذاعة أو اضغط إلغاء العملية:", reply_markup=get_cancel_keyboard())
        bot.register_next_step_handler(prompt, send_broadcast)
        return
    success = 0
    failed = 0
    bot.send_message(message.chat.id, f"⏳ جاري إرسال الإذاعة إلى {len(USERS)} مستخدم...")
    for uid in list(USERS.keys()):
        try:
            bot.send_message(int(uid), f"📢 رسالة من إدارة البوت\n\n{text}")
            success += 1
            time.sleep(0.05)
        except Exception as exc:
            failed += 1
            logger.warning("BROADCAST FAILED | user=%s | error=%s", uid, exc)
    bot.send_message(
        message.chat.id,
        f"✅ انتهت الإذاعة.\n\n📨 تم الإرسال بنجاح: {success}\n❌ فشل الإرسال: {failed}",
        reply_markup=admin_keyboard()
    )


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "📢 إذاعة للمستخدمين")
def admin_broadcast_text(message):
    prompt = bot.send_message(
        message.chat.id,
        "📢 أرسل الآن الرسالة التي تريد إرسالها لكل المستخدمين، أو اضغط إلغاء العملية:",
        reply_markup=get_cancel_keyboard()
    )
    bot.register_next_step_handler(prompt, send_broadcast)


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "إضافة اشتراك يدوي")
def admin_add_text(message):
    prompt = bot.send_message(message.chat.id, "أرسل ID المستخدم وعدد الأيام، مثال: 123456789 30", reply_markup=get_cancel_keyboard())
    bot.register_next_step_handler(prompt, add_manual_subscription)


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "الإحصائيات")
def admin_stats_text(message):
    bot.send_message(message.chat.id, f"📊 الإحصائيات\n👥 المستخدمون: {len(USERS)}\n✅ العمليات الناجحة: {CONFIG.get('total_ops', 0)}\n⏳ الطلبات المعلقة: {len(PENDING_REQUESTS)}\n🔐 الوضع: {'مجاني' if CONFIG.get('is_free') else 'مدفوع'}", reply_markup=admin_keyboard())


@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "العودة للقائمة الرئيسية")
def admin_back_text(message):
    bot.send_message(message.chat.id, "تم الرجوع للقائمة الرئيسية.", reply_markup=get_main_keyboard(message.from_user.id))


@bot.message_handler(func=lambda m: bool(m.text) and ("اشتراك شهر" in m.text or "150جنيه" in m.text or "150 جنيه" in m.text))
def direct_month_subscription(message):
    start_direct_subscription(message, "3")


@bot.message_handler(func=lambda m: bool(m.text) and ("اشتراك 10 أيام" in m.text or "80جنيه" in m.text or "80 جنيه" in m.text))
def direct_ten_day_subscription(message):
    start_direct_subscription(message, "2")


@bot.message_handler(func=lambda m: bool(m.text) and ("اشتراك يوم" in m.text or "15جنيه" in m.text or "15 جنيه" in m.text))
def direct_day_subscription(message):
    start_direct_subscription(message, "1")


@bot.message_handler(func=lambda m: m.text == "💳 تجديد الاشتراك")
def renew_sub(message):
    send_subscription_menu(message)


@bot.message_handler(func=lambda m: m.text == "👤 حسابي")
def my_account(message):
    uid = str(message.from_user.id)
    user = USERS.get(uid, {})
    expire_str = user.get("expire_date")
    if not expire_str:
        bot.send_message(message.chat.id, f"🆔 معرفك: {uid}\n📊 الحالة: لا يوجد اشتراك")
        return
    expire = datetime.fromisoformat(expire_str)
    active = datetime.now(EGYPT_TZ) < expire
    bot.send_message(message.chat.id, f"🆔 معرفك: {uid}\n📊 الحالة: {'✅ مفعل' if active else '❌ منتهي'}\n⏳ ينتهي في: {expire.strftime('%Y-%m-%d %H:%M:%S')}")


@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.send_message(message.chat.id, "استخدم الأزرار الموجودة في القائمة.", reply_markup=get_main_keyboard(message.from_user.id))


def debug_update_listener(messages):
    """يسجل كل تحديث وارد حتى نعرف هل المشكلة من Telegram أم من المعالج."""
    for item in messages:
        try:
            if getattr(item, "data", None):
                logger.info("UPDATE callback | data=%s | user=%s", item.data, item.from_user.id)
            elif getattr(item, "text", None):
                logger.info("UPDATE message | text=%s | user=%s", item.text, item.from_user.id)
            else:
                logger.info("UPDATE received | type=%s", type(item).__name__)
        except Exception:
            logger.exception("UPDATE logging error")


if __name__ == '__main__':
    print("=" * 50)
    print("🤖 Tateer Original King Bot — Started")
    print(f"📅 {datetime.now(EGYPT_TZ).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"👥 مستخدمين محملين: {len(USERS)}")
    print("=" * 50)

    # إشعار الأدمن عند تشغيل البوت
    try:
        bot.send_message(
            ADMIN_ID,
            f"✅ *البوت شغال الآن!*\n"
            f"📅 {datetime.now(EGYPT_TZ).strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"👥 مستخدمين: {len(USERS)}",
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"[STARTUP NOTIFY ERROR] {e}")

    retry_delay = 15
    while True:
        try:
            # إزالة أي Webhook قديم؛ وجوده يمنع polling من استقبال ضغطات الأزرار والرسائل.
            bot.delete_webhook(drop_pending_updates=False)
            me = bot.get_me()
            logger.info("BOT CONNECTED | @%s | id=%s", me.username, me.id)
            logger.info("POLLING started - في انتظار الرسائل والأزرار")
            bot.polling(none_stop=True, interval=0, timeout=60)
        except Exception as e:
            logger.error("POLLING ERROR | %s", e)
            traceback.print_exc()
            try:
                bot.send_message(ADMIN_ID, f"⚠️ خطأ في البولينج:\n{str(e)[:200]}\n\n🔄 إعادة التشغيل خلال {retry_delay} ثانية...")
            except Exception:
                pass
            time.sleep(retry_delay)
