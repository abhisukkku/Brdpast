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
START_IMAGE_URL = os.environ.get("START_IMAGE_URL")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))

# AnonXMusic Database Connection
client = pymongo.MongoClient(MONGODB_URI)
db = client["Anon"]

# Collections
chats_col = db["chats"]         # Groups (chat_id < 0)
users_col = db["tgusersdb"]     # Users (user_id > 0)
blocked_col = db["blockedusers"] 

# ==================== HELPER FUNCTIONS ====================

def is_owner(user_id: int) -> bool:
    return user_id == ADMIN_ID

async def fetch_anon_data():
    """Fetch all groups and users from Anon's database"""
    groups = [chat["chat_id"] for chat in chats_col.find({"chat_id": {"$lt": 0}})]
    users = [user["user_id"] for user in users_col.find({"user_id": {"$gt": 0}})]
    return list(set(groups + users))  # Remove duplicates

async def get_anon_stats():
    """Get statistics from Anon's database"""
    groups = chats_col.count_documents({"chat_id": {"$lt": 0}})
    users = users_col.count_documents({"user_id": {"$gt": 0}})
    blocked = blocked_col.count_documents({})
    return groups, users, blocked

# ==================== COMMANDS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
        [InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=START_IMAGE_URL,
        caption="Welcome to Mikasa File Sharing Bot! 📁",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("🚫 Permission Denied!")
        return
    
    groups, users, blocked = await get_anon_stats()
    stats_text = (
        f"📊 **AnonXMusic Database Stats**\n\n"
        f"• 👥 Groups: `{groups}`\n"
        f"• 👤 Users: `{users}`\n"
        f"• 🚫 Blocked: `{blocked}`"
    )
    await update.message.reply_text(stats_text, parse_mode="Markdown")

# ==================== BROADCAST SYSTEM ====================

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Owner Only Command!")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❗ Reply to a message to broadcast!")
        return

    # Fetch all targets
    targets = await fetch_anon_data()
    total = len(targets)
    
    success_groups = 0
    success_users = 0
    failed_groups = 0
    failed_users = 0

    progress_msg = await update.message.reply_text("🔄 Broadcast Started...")

    for index, chat_id in enumerate(targets, 1):
        try:
            await update.message.reply_to_message.copy(chat_id)
            
            # Check if group or user
            if chat_id < 0:
                success_groups += 1
            else:
                success_users += 1
                
        except Exception as e:
            print(f"Failed to send to {chat_id}: {str(e)}")
            # Update blocked collection
            blocked_col.update_one(
                {"chat_id": chat_id},
                {"$set": {"chat_id": chat_id}},
                upsert=True
            )
            if chat_id < 0:
                failed_groups += 1
            else:
                failed_users += 1
        
        # Update progress every 15 messages
        if index % 15 == 0:
            await progress_msg.edit_text(
                f"⏳ Progress: {index}/{total}\n"
                f"✅ Groups: {success_groups} | Users: {success_users}\n"
                f"❌ Failed G: {failed_groups} | U: {failed_users}"
            )

    # Final report
    report = (
        f"📣 **AnonXMusic Broadcast Report**\n\n"
        f"• Total Targets: {total}\n"
        f"• ✅ Success: {success_groups + success_users}\n"
        f"  - Groups: {success_groups}\n"
        f"  - Users: {success_users}\n"
        f"• ❌ Failed: {failed_groups + failed_users}\n"
        f"  - Groups: {failed_groups}\n"
        f"  - Users: {failed_users}"
    )
    
    await progress_msg.delete()
    await update.message.reply_text(report, parse_mode="Markdown")

# ==================== MAIN ====================

def main():
    app = Application.builder().token(os.environ.get("TOKEN")).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("broadcast", broadcast))
    
    PORT = int(os.environ.get("PORT", 10000))
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=os.environ.get("WEBHOOK_URL"),
        secret_token=os.environ.get("SECRET_TOKEN")
    )

if __name__ == "__main__":
    main()
