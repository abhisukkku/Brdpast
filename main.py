from telegram.ext import filters
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes
)
from motor.motor_asyncio import AsyncIOMotorClient
import os
import asyncio
from datetime import datetime

# Configuration
MONGODB_URI = os.environ.get("MONGODB_URI")
START_IMAGE_URL = os.environ.get("START_IMAGE_URL")
ADMIN_ID = int(os.environ.get("ADMIN_ID"))
LOGGER_GROUP = int(os.environ.get("LOGGER_GROUP"))

# MongoDB Async Setup
client = AsyncIOMotorClient(MONGODB_URI)
db = client["Anon"]
chats_col = db["chats"]
users_col = db["tgusersdb"]
blocked_col = db["blockedusers"]

async def send_log(context: ContextTypes.DEFAULT_TYPE, log_data: str):
    try:
        await context.bot.send_message(LOGGER_GROUP, f"📝 #{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{log_data}", parse_mode="HTML")
    except Exception as e:
        print(f"Log Error: {e}")

def is_owner(user_id: int) -> bool:
    return user_id == ADMIN_ID

async def fetch_valid_targets(context):
    try:
        valid_targets = []
        # Fetch groups
        async for group in chats_col.find({"chat_id": {"$lt": 0}}):
            try:
                chat = await context.bot.get_chat(group["chat_id"])
                if chat.type in ["group", "supergroup"]:
                    valid_targets.append(group["chat_id"])
            except Exception as e:
                print(f"Removing invalid group {group['chat_id']}: {e}")
                await chats_col.delete_one({"_id": group["_id"]})
        
        # Fetch users
        async for user in users_col.find({"user_id": {"$gt": 0}}):
            try:
                await context.bot.get_chat(user["user_id"])
                valid_targets.append(user["user_id"])
            except Exception as e:
                print(f"Removing invalid user {user['user_id']}: {e}")
                await users_col.delete_one({"_id": user["_id"]})
        
        return valid_targets
    except Exception as e:
        print(f"Fetch Targets Error: {e}")
        return []

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not is_owner(update.effective_user.id):
            await update.message.reply_text("❌ Owner Only Command!")
            return

        if not update.message.reply_to_message:
            await update.message.reply_text("❗ Reply to a message to broadcast!")
            return

        # Initial response
        progress_msg = await update.message.reply_text("🔄 Broadcast Initializing...")

        # Fetch targets
        targets = await fetch_valid_targets(context)
        total = len(targets)
        if total == 0:
            await progress_msg.edit_text("❌ No valid targets found!")
            return

        msg_to_broadcast = update.message.reply_to_message
        success_g = success_u = failed_g = failed_u = 0

        # Update progress message
        await progress_msg.edit_text(
            f"⏳ Progress: 0/{total}\n"
            f"✅ Groups: 0 | Users: 0\n"
            f"❌ Failed G: 0 | U: 0"
        )

        # Broadcast loop
        for index, chat_id in enumerate(targets, 1):
            try:
                if chat_id < 0:
                    try:
                        member = await context.bot.get_chat_member(chat_id, context.bot.id)
                        if member.status not in ["administrator", "creator"]:
                            raise Exception("Not admin")
                    except Exception as e:
                        failed_g += 1
                        continue

                await msg_to_broadcast.copy(chat_id=chat_id)
                
                if chat_id < 0: 
                    success_g += 1
                else: 
                    success_u += 1

            except Exception as e:
                print(f"Error in {chat_id}: {str(e)}")
                if chat_id < 0: 
                    failed_g += 1
                else: 
                    failed_u += 1

            # Update progress every 5 messages
            if index % 5 == 0:
                try:
                    await progress_msg.edit_text(
                        f"⏳ Progress: {index}/{total}\n"
                        f"✅ Groups: {success_g} | Users: {success_u}\n"
                        f"❌ Failed G: {failed_g} | U: {failed_u}"
                    )
                except:
                    pass

        # Final report
        report = (
            f"📣 Broadcast Complete!\n"
            f"• Total: {total}\n"
            f"• Success: {success_g + success_u}\n"
            f"• Failed: {failed_g + failed_u}\n"
            f"⚡ Success Rate: {(success_g+success_u)/total*100:.1f}%"
        )
        await context.bot.send_message(update.effective_chat.id, report)
        await progress_msg.delete()

    except Exception as e:
        error_msg = f"🚨 Broadcast Failed: {str(e)}"
        print(error_msg)
        await update.message.reply_text(error_msg)



def main():
    app = Application.builder().token(os.environ.get("TOKEN")).build()
    
    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, group_join_handler))
    
    # Webhook
    PORT = int(os.environ.get("PORT", 10000))
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=os.environ.get("WEBHOOK_URL"),
        secret_token=os.environ.get("SECRET_TOKEN")
    )

if __name__ == "__main__":
    main()
