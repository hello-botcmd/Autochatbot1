"""
Paid Photo module
=================

Flow (driven from the dashboard bot):
  💎 Configure Paid Photo Module
      → pick a connected account
      → dashboard asks for a channel post link
      → the account's userbot verifies it can access that post (it must be
        admin in the channel) and the post is saved to data.json

Runtime (on the account's userbot):
  whenever someone DMs the account a message containing a trigger word
  ("send", "star", ... — alone or inside a sentence), the saved channel
  post is FORWARDED to that DM and the AI auto-reply stays silent for
  that message (see the skip check in aichat.py).
"""

import re
import time

from pyrogram import Client, filters
from pyrogram.types import Message

from aichat import load_data, save_data

# ----------------------------------------------------------------------
# TRIGGERS — add your own words here. Matching is word-based, so "send",
# ".send", "Send!" and "please send me" all trigger the paid photo.
# ----------------------------------------------------------------------
TRIGGER_WORDS = {"send", "star"}

# Don't re-send the photo to the same user more often than this (anti-spam).
RESEND_COOLDOWN_SECONDS = 10

# peer_id -> last forward timestamp
_last_photo_sent = {}


# ----------------------------------------------------------------------
# Helpers used by other modules
# ----------------------------------------------------------------------

def is_photo_trigger(text) -> bool:
    """True if the text contains any trigger word (standalone or in a sentence)."""
    if not text:
        return False
    tokens = re.split(r"[^a-z0-9_]+", text.lower())
    return any(token in TRIGGER_WORDS for token in tokens)


def get_paid_photo(owner_id: str):
    """Return the saved paid-photo config for an account, or None."""
    data = load_data()
    return data.get("users", {}).get(str(owner_id), {}).get("paid_photo")


def parse_post_link(link: str):
    """
    Parse a public t.me post link into (chat, message_id).

    Supports:
      https://t.me/channelusername/12       (public channel)
      https://t.me/s/channelusername/12     (web-preview variant)
      https://t.me/c/1234567890/12          (private channel)
      https://t.me/channelusername/12?single  (query strings are stripped)

    Returns None if the link doesn't match.
    """
    link = link.strip().split("?", 1)[0].rstrip("/")

    # Private channel link -> -100<id>
    m = re.match(r"^(?:https?://)?t\.me/c/(\d+)/(\d+)$", link)
    if m:
        return int(f"-100{m.group(1)}"), int(m.group(2))

    # Public username link
    m = re.match(r"^(?:https?://)?t\.me/(?:s/)?([A-Za-z0-9_]{4,})/(\d+)$", link)
    if m:
        return m.group(1), int(m.group(2))

    return None


async def verify_and_save_post(user_client: Client, owner_id: str, link: str):
    """
    Verify a channel post via the account's userbot and save it as that
    account's paid photo. Returns (ok: bool, message_for_user: str).
    """
    parsed = parse_post_link(link)
    if not parsed:
        return False, (
            "❌ **Invalid link**\n\n"
            "Send a Telegram post link like:\n"
            "• `https://t.me/yourchannel/12`\n"
            "• `https://t.me/c/1234567890/12` (private channel)"
        )

    chat, message_id = parsed

    try:
        msg = await user_client.get_messages(chat, message_id)
    except Exception as e:
        return False, (
            "❌ **Couldn't access that post.**\n\n"
            f"Make sure this account is **admin** in the channel.\n\n`{e}`"
        )

    if not msg or msg.empty:
        return False, "❌ **Post not found** — double-check the link."

    if not msg.photo:
        return False, (
            "❌ **That post has no photo.**\n\n"
            "Link the post that contains your photo (with stars)."
        )

    chat_title = msg.chat.title or msg.chat.username or str(msg.chat.id)
    protected = bool(
        getattr(msg, "has_protected_content", False)
        or getattr(msg.chat, "has_protected_content", False)
    )

    data = load_data()
    data.setdefault("users", {}).setdefault(str(owner_id), {})["paid_photo"] = {
        "chat_id": msg.chat.id,
        "chat_title": chat_title,
        "message_id": message_id,
        "link": link.strip(),
        "protected": protected,
    }
    save_data(data)

    warn = (
        "\n\n⚠️ This channel **restricts forwarding** — I'll try to copy the photo instead."
        if protected else ""
    )
    triggers = ", ".join(f"`{w}`" for w in sorted(TRIGGER_WORDS))
    return True, (
        f"✅ **Paid photo set for this account!**\n\n"
        f"• **Channel:** `{chat_title}`\n"
        f"• **Post:** `#{message_id}`\n\n"
        f"Now when someone DMs this account a message containing {triggers}, "
        f"this post is forwarded and AI stays silent for that message.{warn}"
    )


# ----------------------------------------------------------------------
# Userbot handler registration (called from main.py per connected account)
# ----------------------------------------------------------------------

def register_sendphoto_handler(user_client: Client, owner_id: str):
    """Register the paid-photo DM trigger on an account's userbot client."""

    @user_client.on_message(
        filters.private & ~filters.me & ~filters.bot & ~filters.service
    )
    async def paid_photo_trigger(client: Client, message: Message):
        if not message.text or not message.from_user:
            return

        owner_id_str = str(owner_id)
        data = load_data()
        uinfo = data.get("users", {}).get(owner_id_str, {})

        # Only active when a post is configured for this account
        photo_cfg = uinfo.get("paid_photo")
        if not photo_cfg:
            return

        # Reuse the AI blocklist: blocked users get nothing
        if str(message.from_user.id) in data.get("blocked", []):
            return

        if not is_photo_trigger(message.text):
            return

        # Small anti-spam cooldown per DM
        peer = str(message.chat.id)
        now = time.time()
        if now - _last_photo_sent.get(peer, 0) < RESEND_COOLDOWN_SECONDS:
            return
        _last_photo_sent[peer] = now

        # Forward the channel post (keeps the channel attribution)
        try:
            await client.forward_messages(
                chat_id=message.chat.id,
                from_chat_id=photo_cfg["chat_id"],
                message_ids=photo_cfg["message_id"],
            )
            return
        except Exception as e:
            print(f"[sendphoto] forward failed, trying copy: {e}")

        # Fallback: forward-restricted channels -> copy the photo
        try:
            src = await client.get_messages(
                photo_cfg["chat_id"], photo_cfg["message_id"]
            )
            await src.copy(message.chat.id)
        except Exception as e:
            print(f"[sendphoto] copy also failed: {e}")
