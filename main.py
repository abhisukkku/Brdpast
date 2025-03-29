from telegram.ext import filters
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler
)
import os
import pymongo

# MongoDB Setup
MONGODB_URI = os.environ.get("MONGODB_URI")
LOGGER_GROUP = int(os.environ.get("LOGGER_GROUP"))
START_IMAGE_URL = os.environ.get("START_IMAGE_URL")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))

client = pymongo.MongoClient(MONGODB_URI)

# Databases
db_emiko = client["EmikoBotDB"]
db_anon = client["Anon"]

# Collections
emiko_chats = db_emiko["chats"]
emiko_blocked = db_emiko["blocked"]
anon_chats = db_anon["chats"]
anon_users = db_anon["tgusersdb"]
anon_blocked = db_anon["blockedusers"]

# ==================== HELPER FUNCTIONS ====================

def is_owner(user_id: int) -> bool:
    return user_id == ADMIN_ID

async def get_combined_stats():
    # Emiko Stats
    emiko_groups = emiko_chats.count_documents({"type": "group"})
    emiko_users = emiko_chats.count_documents({"type": "private"})
    
    # Anon Stats
    anon_groups = anon_chats.count_documents({"chat_id": {"$lt": 0}})
    anon_users_count = anon_users.count_documents({"user_id": {"$gt": 0}})
    
    # Blocked Stats
    total_blocked = emiko_blocked.count_documents({}) + anon_blocked.count_documents({})
    
    return (
        emiko_groups + anon_groups,
        emiko_users + anon_users_count,
        total_blocked
    )

# ==================== COMMAND HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
        [InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=START_IMAGE_URL,
        caption="🌸 **Hii~ I'ᴍ Emiko!** 🌸\n\nYour ultimate group manager bot!",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("🚫 Access Denied!")
        return
    
    groups, users, blocked = await get_combined_stats()
    stats_msg = (
        f"📊 **loda Bot Statistics**\n\n"
        f"• 🚫 Blocked Users: `{blocked}`\n"
        f"• 👥 Groups Managed: `{groups}`\n"
        f"• 👤 Total Users: `{users}`"
    )
    await update.message.reply_text(stats_msg, parse_mode="Markdown")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Administrator Only!")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("🔍 Please reply to a message to broadcast!")
        return

    # Collect all chat IDs
    all_chats = []
    
    # From Emiko
    for chat in emiko_chats.find():
        all_chats.append(chat["chat_id"])
    
    # From AnonXMusic
    for group in anon_chats.find({"chat_id": {"$lt": 0}}):
        all_chats.append(group["chat_id"])
    for user in anon_users.find({"user_id": {"$gt": 0}}):
        all_chats.append(user["user_id"])
    
    unique_chats = list(set(all_chats))
    total = len(unique_chats)
    success = 0
    failed = 0

    progress_msg = await update.message.reply_text(
        f"📤 Broadcasting started...\n0/{total} sent",
        parse_mode="Markdown"
    )

    for index, chat_id in enumerate(unique_chats, 1):
        try:
            await update.message.reply_to_message.copy(chat_id)
            success += 1
        except Exception as e:
            print(f"Failed to send to {chat_id}: {e}")
            failed += 1
            # Update both blocked collections
            emiko_blocked.update_one(
                {"chat_id": chat_id},
                {"$set": {"chat_id": chat_id}},
                upsert=True
            )
            anon_blocked.update_one(
                {"chat_id": chat_id},
                {"$set": {"chat_id": chat_id}},
                upsert=True
            )
        
        # Update progress every 20 messages
        if index % 20 == 0:
            await progress_msg.edit_text(
                f"⏳ Progress: {index}/{total}\n✅ Success: {success}\n❌ Failed: {failed}"
            )

    # Final report
    report_msg = (
        f"📣 **Broadcast Complete**\n\n"
        f"• Total Targets: `{total}`\n"
        f"• ✅ Success: `{success}`\n"
        f"• ❌ Failed: `{failed}`"
    )
    
    await progress_msg.delete()
    await update.message.reply_text(report_msg, parse_mode="Markdown")

# ==================== MAIN ====================

def main():
    app = Application.builder().token(os.environ.get("TOKEN")).build()
    
    # Command Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("broadcast", broadcast))
    
    # Webhook Setup
    PORT = int(os.environ.get("PORT", 10000))
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=os.environ.get("WEBHOOK_URL"),
        secret_token=os.environ.get("SECRET_TOKEN")
    )

if __name__ == "__main__":
    main()
