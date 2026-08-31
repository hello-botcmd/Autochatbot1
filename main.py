import asyncio
import os
import time
from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from aichat import load_data, register_ai_handler, save_data
from sendphoto import (
    TRIGGER_WORDS,
    register_sendphoto_handler,
    verify_and_save_post,
)
from stats import get_stats_text

load_dotenv()

API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "sexyiwowu")

START_PIC_URL = "https://images.unsplash.com/photo-1503376780353-7e6692767b70"

connected_clients = {}
user_states = {}

bot = Client("DashboardBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


def get_start_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 Dashboard", callback_data="back_main")],
        [InlineKeyboardButton("📞 Contact Support", url=f"https://t.me/{SUPPORT_USERNAME}")],
    ])


def get_dashboard_markup():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Add Account", callback_data="add_acc"),
            InlineKeyboardButton("🗄 Manage Accounts", callback_data="manage_acc"),
        ],
        [
            InlineKeyboardButton("⚡ Toggle AI", callback_data="toggle_ai"),
            InlineKeyboardButton("📊 System Stats", callback_data="stats"),
        ],
        [
            InlineKeyboardButton("💎 Configure Paid Photo Module", callback_data="set_photo_menu"),
        ],
        [
            InlineKeyboardButton("⬅️ Home Menu", callback_data="back_start"),
        ],
    ])


@bot.on_message(filters.command("start") & filters.private)
async def start_handler(client, message: Message):
    text = (
        "✨ **Welcome to Control Panel** ✨\n\n"
        "Manage your active string session userbots, set custom auto-reply triggers, and control AI modules."
    )
    try:
        await message.reply_photo(photo=START_PIC_URL, caption=text, reply_markup=get_start_markup())
    except Exception:
        await message.reply_text(text, reply_markup=get_start_markup())


@bot.on_callback_query()
async def callback_handler(client, query: CallbackQuery):
    user_id = str(query.from_user.id)
    data = load_data()

    if query.data == "back_start":
        text = (
            "✨ **Welcome to Control Panel** ✨\n\n"
            "Manage your active string session userbots, set custom auto-reply triggers, and control AI modules."
        )
        if query.message.photo:
            await query.message.edit_caption(caption=text, reply_markup=get_start_markup())
        else:
            await query.message.edit_text(text, reply_markup=get_start_markup())

    elif query.data == "back_main":
        user_states.pop(user_id, None)
        text = (
            "📂 **Userbot Dashboard**\n\n"
            "• **➕ Add Account** — Connect Pyrogram String Session\n"
            "• **🗄 Manage Accounts** — View connected account status\n"
            "• **⚡ Toggle AI** — Turn AI Auto-Reply ON / OFF\n"
            "• **💎 Paid Photo Settings** — Configure Channel & IDs for auto-send\n"
            "• **📊 System Stats** — VPS & CPU Performance"
        )
        if query.message.photo:
            await query.message.delete()
            await query.message.reply_text(text, reply_markup=get_dashboard_markup())
        else:
            await query.message.edit_text(text, reply_markup=get_dashboard_markup())

    elif query.data == "add_acc":
        user_states[user_id] = "AWAITING_SESSION"
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Cancel", callback_data="back_main")]
        ])
        await query.message.edit_text(
            "🔐 **Send Pyrogram String Session**\n\n"
            "Paste your String Session below to link your account to the bot.",
            reply_markup=markup
        )

    elif query.data == "set_photo_menu":
        saved_users = data.get("users", {})
        btns = []
        for uid in connected_clients:
            uinfo = saved_users.get(uid, {})
            name = uinfo.get("name", f"User {uid}")
            cfg = uinfo.get("paid_photo")
            marker = "💎" if cfg else "➕"
            label = f"{marker} {name}" + (f" — {cfg.get('chat_title')}" if cfg else "")
            btns.append([InlineKeyboardButton(label, callback_data=f"setphoto_acc_{uid}")])

        if btns:
            triggers = ", ".join(f"`{w}`" for w in sorted(TRIGGER_WORDS))
            text = (
                "💎 **Paid Photo Module**\n\n"
                "Select an account to configure its paid photo:\n\n"
                "➕ no photo set · 💎 photo configured\n\n"
                f"When someone DMs the account a message containing {triggers} "
                "(alone or inside a sentence), the channel post is forwarded "
                "and AI stays silent for that message."
            )
        else:
            text = (
                "💎 **Paid Photo Module**\n\n"
                "No accounts are connected right now. Add an account first."
            )

        btns.append([InlineKeyboardButton("⬅️ Back to Dashboard", callback_data="back_main")])
        await query.answer()
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(btns))

    elif query.data.startswith("setphoto_acc_"):
        target_uid = query.data.replace("setphoto_acc_", "")
        if target_uid not in connected_clients:
            await query.answer("That account is offline — reconnect it first!", show_alert=True)
            return

        cfg = data.get("users", {}).get(target_uid, {}).get("paid_photo")
        if cfg:
            current = (
                f"📸 **Current post:** `{cfg.get('chat_title')}` · "
                f"[post #{cfg.get('message_id')}]({cfg.get('link')})\n\n"
                "Sending a new link will replace it."
            )
        else:
            current = "📸 **Current post:** none"

        user_states[user_id] = f"AWAITING_PHOTO_LINK:{target_uid}"
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Cancel", callback_data="set_photo_menu")]
        ])
        await query.answer()
        await query.message.edit_text(
            "💎 **Set Paid Photo**\n\n"
            f"{current}\n\n"
            "🔗 Send the **link of the channel post** (your photo with stars).\n\n"
            "• The account must be **admin** in that channel\n"
            "• Link format: `https://t.me/yourchannel/12`",
            reply_markup=markup,
            disable_web_page_preview=True,
        )

    elif query.data == "manage_acc":
        saved_users = data.get("users", {})
        text = "🗄 **Connected Accounts**\n\n"
        text += "🟢 = Active & Connected | 🔴 = AI Disabled / Disconnected\n\n"

        btns = []
        for uid, uinfo in saved_users.items():
            is_active = uid in connected_clients
            ai_on = uinfo.get("ai_enabled", True)
            indicator = "🟢" if (is_active and ai_on) else ("🔴" if is_active else "⚪ Disconnected")
            acc_name = uinfo.get("name", f"User {uid}")
            btns.append([InlineKeyboardButton(f"{indicator} {acc_name}", callback_data=f"view_acc_{uid}")])

        btns.append([InlineKeyboardButton("⬅️ Back to Dashboard", callback_data="back_main")])
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(btns))

    elif query.data.startswith("view_acc_"):
        target_uid = query.data.replace("view_acc_", "")
        saved_users = data.get("users", {})
        uinfo = saved_users.get(target_uid, {})

        if not uinfo:
            await query.answer("Account data missing!", show_alert=True)
            return

        is_connected = target_uid in connected_clients
        ai_status = "ON ✅" if uinfo.get("ai_enabled", True) else "OFF ❌"
        conn_status = "Connected 🟢" if is_connected else "Offline 🔴"
        acc_name = uinfo.get("name", "Unknown User")
        photo_cfg = uinfo.get("paid_photo")
        photo_status = f"✅ {photo_cfg.get('chat_title')} #{photo_cfg.get('message_id')}" if photo_cfg else "❌ Not set"

        text = (
            f"👤 **Account Management**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• **Name:** `{acc_name}`\n"
            f"• **User ID:** `{target_uid}`\n"
            f"• **Session Status:** {conn_status}\n"
            f"• **AI Auto-Reply:** {ai_status}\n"
            f"• **Paid Photo:** {photo_status}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )

        btns = [
            [InlineKeyboardButton("⚡ Toggle AI Status", callback_data=f"toggle_acc_ai_{target_uid}")],
            [InlineKeyboardButton("❌ Disconnect Account", callback_data=f"term_acc_{target_uid}")],
            [InlineKeyboardButton("⬅️ Back to List", callback_data="manage_acc")]
        ]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(btns))

    elif query.data.startswith("toggle_acc_ai_"):
        target_uid = query.data.replace("toggle_acc_ai_", "")
        if target_uid in data.get("users", {}):
            curr = data["users"][target_uid].get("ai_enabled", True)
            data["users"][target_uid]["ai_enabled"] = not curr
            save_data(data)
            status_text = "ON ✅" if not curr else "OFF ❌"
            await query.answer(f"AI Status set to {status_text}", show_alert=True)
            query.data = f"view_acc_{target_uid}"
            await callback_handler(client, query)

    elif query.data.startswith("term_acc_"):
        target_uid = query.data.replace("term_acc_", "")
        if target_uid in connected_clients:
            try:
                await connected_clients[target_uid].stop()
            except Exception:
                pass
            del connected_clients[target_uid]

        if target_uid in data.get("users", {}):
            data["users"].pop(target_uid, None)
            save_data(data)

        await query.answer("Session removed successfully!", show_alert=True)
        query.data = "manage_acc"
        await callback_handler(client, query)

    elif query.data == "toggle_ai":
        users = data.get("users", {})
        if not users:
            await query.answer("No accounts connected!", show_alert=True)
            return

        first_uid = next(iter(users))
        new_state = not users[first_uid].get("ai_enabled", True)
        for uid in users:
            users[uid]["ai_enabled"] = new_state
        save_data(data)

        status = "ON ✅" if new_state else "OFF ❌"
        await query.answer(f"Global AI Auto-Reply set to: {status}", show_alert=True)

    elif query.data == "stats":
        stats_text = get_stats_text(connected_clients, data)
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh Stats", callback_data="stats")],
            [InlineKeyboardButton("⬅️ Back to Dashboard", callback_data="back_main")]
        ])
        await query.message.edit_text(stats_text, reply_markup=markup)


@bot.on_message(filters.private & ~filters.command(["start"]))
async def user_input_handler(client, message: Message):
    user_id = str(message.from_user.id)
    state = user_states.get(user_id)

    if state and state.startswith("AWAITING_PHOTO_LINK:"):
        target_uid = state.split(":", 1)[1]
        status_msg = await message.reply_text("🔄 Verifying channel post...")

        if message.text is None:
            await status_msg.edit_text("❌ Please send the post **link as text**.")
            return

        target_client = connected_clients.get(target_uid)
        if not target_client:
            user_states.pop(user_id, None)
            await status_msg.edit_text(
                "❌ That account went offline. Reconnect it and try again."
            )
            return

        ok, result = await verify_and_save_post(target_client, target_uid, message.text)
        if ok:
            user_states.pop(user_id, None)

        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 Paid Photo Menu", callback_data="set_photo_menu")],
            [InlineKeyboardButton("⬅️ Back to Dashboard", callback_data="back_main")],
        ])
        await status_msg.edit_text(result, reply_markup=markup, disable_web_page_preview=True)
        return

    if state == "AWAITING_SESSION":
        if message.text is None:
            await message.reply_text("❌ Please paste the string session as text.")
            return

        session_string = message.text.strip()
        status_msg = await message.reply_text("🔄 Validating & connecting string session...")

        try:
            user_client = Client(
                name=f"ub_{user_id}_{int(time.time())}",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=session_string,
                in_memory=True
            )

            await user_client.start()
            me = await user_client.get_me()
            acc_uid = str(me.id)
            acc_name = me.first_name or f"User {acc_uid}"

            # Register dynamic userbot handlers specifically for this session
            register_ai_handler(user_client, acc_uid, OPENROUTER_API_KEY)
            register_sendphoto_handler(user_client, acc_uid)
            connected_clients[acc_uid] = user_client

            data = load_data()
            data.setdefault("users", {})[acc_uid] = {
                "name": acc_name,
                "session": session_string,
                "ai_enabled": True,
                "history": {},
            }
            save_data(data)

            user_states.pop(user_id, None)

            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🗄 Manage Accounts", callback_data="manage_acc")],
                [InlineKeyboardButton("⬅️ Return to Dashboard", callback_data="back_main")]
            ])

            await status_msg.edit_text(
                f"✅ **Session Successfully Connected!**\n\n"
                f"• **Account Name:** `{acc_name}`\n"
                f"• **User ID:** `{acc_uid}`\n"
                f"• **Auto Photo Trigger:** Configure via 💎 Paid Photo Menu (`send`, `star`)",
                reply_markup=markup
            )

        except Exception as e:
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back to Dashboard", callback_data="back_main")]
            ])
            await status_msg.edit_text(
                f"❌ **Failed to Connect Session:** `{e}`",
                reply_markup=markup
            )


async def main():
    await bot.start()
    print("Dashboard Control Panel Started!")

    # Restore session instances on service boot
    data = load_data()
    for uid, udata in data.get("users", {}).items():
        try:
            cli = Client(
                name=f"ub_{uid}",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=udata["session"],
                in_memory=True
            )
            register_ai_handler(cli, uid, OPENROUTER_API_KEY)
            register_sendphoto_handler(cli, uid)
            await cli.start()
            connected_clients[str(uid)] = cli
            print(f"Session Active: {uid}")
        except Exception as e:
            print(f"Failed Session Restore for {uid}: {e}")

    await asyncio.Event().wait()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
