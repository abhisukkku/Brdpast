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
from datetime import datetime

# MongoDB Setup
MONGODB_URI = os.environ.get("MONGODB_URI")
START_IMAGE_URL = os.environ.get("START_IMAGE_URL")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))
LOGGER_GROUP = int(os.environ.get("LOGGER_GROUP"))  # Log channel ID

# AnonXMusic Database Connection
client = pymongo.MongoClient(MONGODB_URI)
db = client["Anon"]

# Collections
chats_col = db["chats"]         # Groups (chat_id < 0)
users_col = db["tgusersdb"]     # Users (user_id > 0)
blocked_col = db["blockedusers"] 

async def send_log(context: ContextTypes.DEFAULT_TYPE, log_data: str):
    """Send logs to logger channel"""
    try:
        await context.bot.send_message(
            chat_id=LOGGER_GROUP,
            text=f"📝 #{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{log_data}",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Logging Error: {e}")

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
    user = update.effective_user
    log_msg = (
        f"🆕 New User Started Bot\n"
        f"• ID: <code>{user.id}</code>\n"
        f"• Username: @{user.username}\n"
        f"• Name: {user.full_name}"
    )
    await send_log(context, log_msg)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Join", url="https://t.me/Hanime_Japan"),
            InlineKeyboardButton("Join", url="https://t.me/Anime_Samurais")
        ],
        [
            InlineKeyboardButton("Join", url="https://t.me/FinishedAnimeList"),
            InlineKeyboardButton("Join", url="https://t.me/Hanimee_Lovers")
        ]
    ])
    
    await context.bot.send_photo(
        chat_id=update.effective_chat.id,
        photo=START_IMAGE_URL,
        caption=" **Welcome to Mikasa File Sharing Bot! 📁✨** \n\nEasily upload, store, and share your files with just a tap! 🚀",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def group_join_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bot being added to a group"""
    chat = update.effective_chat
    user = update.effective_user
    
    log_msg = (
        f"👥 Bot Added to New Group\n"
        f"• Group ID: <code>{chat.id}</code>\n"
        f"• Group Name: {chat.title}\n"
        f"• Added by: @{user.username} (<code>{user.id}</code>)"
    )
    
    await send_log(context, log_msg)
    
    # Add group to database
    if not await chats_col.find_one({"chat_id": chat.id}):
        await chats_col.insert_one({
            "chat_id": chat.id,
            "title": chat.title,
            "type": "group"
        })

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("🚫 Permission Denied!")
        return
    
    groups, users, blocked = await get_anon_stats()
    stats_text = (
        f"📊 **MikasaXFile Database Stats**\n\n"
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
    msg_to_broadcast = update.message.reply_to_message

    for index, chat_id in enumerate(targets, 1):
        try:
            # Check if bot is admin in groups
            if chat_id < 0:
                try:
                    chat_member = await context.bot.get_chat_member(chat_id, context.bot.id)
                    if chat_member.status not in ["administrator", "creator"]:
                        raise Exception("Not admin in group")
                except Exception as e:
                    print(f"Admin check failed for {chat_id}: {str(e)}")
                    failed_groups += 1
                    continue

            # Forwarding logic improvement
            if msg_to_broadcast.forward_from_chat:
                # For channel forwards
                await msg_to_broadcast.forward(chat_id=chat_id)
            elif msg_to_broadcast.forward_from:
                # For user forwards
                await msg_to_broadcast.copy(chat_id=chat_id)
            else:
                # Normal message
                await msg_to_broadcast.copy(chat_id=chat_id)
            
            # Update success counts
            if chat_id < 0:
                success_groups += 1
            else:
                success_users += 1
                
        except Exception as e:
            error_msg = f"Failed to send to {chat_id}: {str(e)}"
            print(error_msg)
            
            # Special handling for flood waits
            if "FloodWait" in str(e):
                flood_time = int(str(e).split()[-1])
                await asyncio.sleep(flood_time)
                continue
                
            # Update blocked list only for critical errors
            if "Forbidden" in str(e) or "Unauthorized" in str(e):
                blocked_col.update_one(
                    {"chat_id": chat_id},
                    {"$set": {"chat_id": chat_id}},
                    upsert=True
                )
            
            # Update failure counts
            if chat_id < 0:
                failed_groups += 1
            else:
                failed_users += 1
        
        # Update progress every 10 messages with slower rate
        if index % 10 == 0:
            try:
                await progress_msg.edit_text(
                    f"⏳ Progress: {index}/{total}\n"
                    f"✅ Groups: {success_groups} | Users: {success_users}\n"
                    f"❌ Failed G: {failed_groups} | U: {failed_users}"
                )
                await asyncio.sleep(1)  # Add small delay to avoid flooding
            except Exception as e:
                print(f"Progress update failed: {str(e)}")

    # Final report
    report = (
        f"📣 **MikasaXFile Broadcast Report**\n\n"
        f"• Total Targets: {total}\n"
        f"• ✅ Success: {success_groups + success_users}\n"
        f"  - Groups: {success_groups}\n"
        f"  - Users: {success_users}\n"
        f"• ❌ Failed: {failed_groups + failed_users}\n"
        f"  - Groups: {failed_groups}\n"
        f"  - Users: {failed_users}"
    )
    
    try:
        await progress_msg.delete()
    except Exception as e:
        print(f"Failed to delete progress message: {str(e)}")
    
    await update.message.reply_text(report, parse_mode="Markdown")

# ==================== MAIN ====================
def main():
    app = Application.builder().token(os.environ.get("TOKEN")).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("broadcast", broadcast))
    
    # Group join handler
    app.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS, 
        group_join_handler
    ))
    
    # Webhook setup
    PORT = int(os.environ.get("PORT", 10000))
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=os.environ.get("WEBHOOK_URL"),
        secret_token=os.environ.get("SECRET_TOKEN")
    )

if __name__ == "__main__":
    main()
