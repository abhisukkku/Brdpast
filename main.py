from telegram.ext import filters
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler
)
from datetime import datetime
import os
import pymongo

# MongoDB Setup
MONGODB_URI = os.environ.get("MONGODB_URI")
LOGGER_GROUP = int(os.environ.get("LOGGER_GROUP"))
START_IMAGE_URL = os.environ.get("START_IMAGE_URL")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))

client = pymongo.MongoClient(MONGODB_URI)

# Emiko Database
db_emiko = client["EmikoBotDB"]
chats_collection_emiko = db_emiko["chats"]
blocked_collection_emiko = db_emiko["blocked"]

# AnonXMusic Database
db_anon = client["Anon"]
chats_collection_anon = db_anon["chats"]          # Groups (chat_id < 0)
users_collection_anon = db_anon["tgusersdb"]      # Users (user_id > 0)
blocked_collection_anon = db_anon["blockedusers"] # Blocked Users

# ==================== HELPER FUNCTIONS ====================

def is_owner(user_id: int) -> bool:
    return user_id == ADMIN_ID

async def is_bot_admin(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
        return bot_member.status in ["administrator", "creator"]
    except Exception as e:
        print(f"Bot Admin Check Error: {e}")
        return False

async def get_stats():
    # Emiko Data
    emiko_groups = chats_collection_emiko.count_documents({"type": "group"})
    emiko_users = chats_collection_emiko.count_documents({"type": "private"})
    
    # AnonXMusic Data
    anon_groups = chats_collection_anon.count_documents({"chat_id": {"$lt": 0}})
    anon_users = users_collection_anon.count_documents({"user_id": {"$gt": 0}})
    
    # Blocked Users
    blocked_emiko = blocked_collection_emiko.count_documents({})
    blocked_anon = blocked_collection_anon.count_documents({})
    
    # Combined Stats
    total_groups = emiko_groups + anon_groups
    total_users = emiko_users + anon_users
    total_blocked = blocked_emiko + blocked_anon
    
    return total_groups, total_users, total_blocked

# ==================== CORE FUNCTIONS ====================

async def store_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    # Store in Emiko's DB
    if not chats_collection_emiko.find_one({"chat_id": chat.id}):
        chat_type = "group" if chat.type in ["group", "supergroup"] else "private"
        chats_collection_emiko.insert_one({"chat_id": chat.id, "type": chat_type})

# ==================== COMMANDS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await store_chat_id(update, context)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
        [InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=START_IMAGE_URL,
        caption="🌸 **Hii~ I'ᴍ Emiko!** 🌸\n\nI'm here to keep your group fun and managed! (≧▽≦)\n\nUse buttons below to interact! (✿◕‿◕)♡",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("🚫 You don't have permission!", parse_mode="Markdown")
        return
    
    groups, users, blocked = await get_stats()
    bot_name = f"[Emiko Bot](https://t.me/{context.bot.username})"
    stats_text = f"""
**{bot_name} Combined Stats (Emiko + AnonXMusic):**
**📛 Blocked Users:** `{blocked}`
**👥 Groups:** `{groups}`
**👤 Users:** `{users}`
    """
    await update.message.reply_text(stats_text.strip(), parse_mode="Markdown")

# ==================== BROADCAST SYSTEM ====================

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_owner(user.id):
        await update.message.reply_text("❌ You're not authorized!", parse_mode="Markdown")
        return
    
    reply_msg = update.message.reply_to_message
    if not reply_msg:
        await update.message.reply_text("Reply to a message to broadcast!", parse_mode="Markdown")
        return
    
    # Collect all chat IDs from both databases
    all_chats = []
    
    # From Emiko's DB
    for chat in chats_collection_emiko.find():
        all_chats.append(chat["chat_id"])
    
    # From AnonXMusic's DB
    # Groups (negative IDs)
    for group in chats_collection_anon.find({"chat_id": {"$lt": 0}}):
        all_chats.append(group["chat_id"])
    
    # Users (positive IDs)
    for user in users_collection_anon.find({"user_id": {"$gt": 0}}):
        all_chats.append(user["user_id"])
    
    # Remove duplicates
    unique_chats = list(set(all_chats))
    
    groups = 0
    users = 0
    failed = 0
    
    for chat_id in unique_chats:
        try:
            if reply_msg.forward_from_chat or reply_msg.forward_from:
                await reply_msg.forward(chat_id=chat_id)
            else:
                await reply_msg.copy(chat_id=chat_id)
            
            # Count as group if ID is negative
            if chat_id < 0:
                groups += 1
            else:
                users += 1
                
        except Exception as e:
            print(f"Broadcast Error: {e}")
            failed += 1
            # Add to both blocked collections
            blocked_collection_emiko.update_one(
                {"chat_id": chat_id},
                {"$set": {"chat_id": chat_id}},
                upsert=True
            )
            blocked_collection_anon.update_one(
                {"chat_id": chat_id},
                {"$set": {"chat_id": chat_id}},
                upsert=True
            )
    
    await update.message.reply_text(
        f"✅ **Combined Broadcast Report:**\n👥 Groups: `{groups}`\n👤 Users: `{users}`\n❌ Failed: `{failed}`",
        parse_mode="Markdown"
    )

# ==================== MAIN ====================

def main():
    app = Application.builder().token(os.environ.get("TOKEN")).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(MessageHandler(filters.ALL, store_chat_id))
    
    PORT = int(os.environ.get("PORT", 10000))
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=os.environ.get("WEBHOOK_URL"),
        secret_token=os.environ.get("SECRET_TOKEN")
    )

if __name__ == "__main__":
    main()
