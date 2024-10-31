import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest
from telegram.constants import ChatMemberStatus
import sqlite3

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Database setup
conn = sqlite3.connect('users.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users
             (user_id INTEGER PRIMARY KEY, username TEXT, invited_count INTEGER, 
              channels_followed INTEGER, referrer_id INTEGER)''')
conn.commit()

# Constants
REQUIRED_INVITES = 5
CHANNEL_LINK = "https://t.me/+GmCMsWCTsZYyMzhi"
CHANNELS_TO_FOLLOW = ["@english_avenue", "@ielts_bus"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username

    # Check if user was referred
    referrer_id = None
    if context.args and context.args[0].isdigit():
        referrer_id = int(context.args[0])

    # Register user in the database
    c.execute("INSERT OR IGNORE INTO users (user_id, username, invited_count, channels_followed, referrer_id) VALUES (?, ?, ?, ?, ?)", 
              (user_id, username, 0, 0, referrer_id))
    conn.commit()

    # Ask user to follow channels
    await send_channel_list(update, context)

async def send_channel_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    for channel in CHANNELS_TO_FOLLOW:
        keyboard.append([InlineKeyboardButton(text=f"Join {channel}", url=f"https://t.me/{channel[1:]}")])
    keyboard.append([InlineKeyboardButton(text="✅ I've followed all channels", callback_data="check_subscription")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🔔 Welcome! Please join these channels to continue:",
        reply_markup=reply_markup
    )

async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    
    all_followed = True
    not_followed = []

    for channel in CHANNELS_TO_FOLLOW:
        try:
            chat_member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if chat_member.status not in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                all_followed = False
                not_followed.append(channel)
        except BadRequest as e:
            logger.error(f"Error checking membership for {channel}: {e}")
            all_followed = False
            not_followed.append(channel)

    if all_followed:
        # Update user's status
        c.execute("UPDATE users SET channels_followed = 1 WHERE user_id = ?", (user_id,))
        conn.commit()

        # Check if this user was referred and update referrer's count if necessary
        c.execute("SELECT referrer_id FROM users WHERE user_id = ?", (user_id,))
        referrer_id = c.fetchone()[0]
        if referrer_id:
            c.execute("UPDATE users SET invited_count = invited_count + 1 WHERE user_id = ?", (referrer_id,))
            conn.commit()
            
            # Check if the referrer has reached the required invites
            c.execute("SELECT invited_count FROM users WHERE user_id = ?", (referrer_id,))
            invited_count = c.fetchone()[0]
            if invited_count >= REQUIRED_INVITES:
                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=f"📣Congratulations! You have invited {REQUIRED_INVITES} friends. "
                             f"You can now join the channel via this link 🔗: {CHANNEL_LINK}"
                    )
                except Exception as e:
                    logger.error(f"Failed to send channel link to user {referrer_id}: {e}")

        await show_main_menu(update, context)
    else:
        # Create a new keyboard with only the channels the user hasn't joined
        keyboard = []
        for channel in not_followed:
            keyboard.append([InlineKeyboardButton(text=f"Join {channel}", url=f"https://t.me/{channel[1:]}")])
        keyboard.append([InlineKeyboardButton(text="✅ I've followed all channels", callback_data="check_subscription")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "❌ You haven't joined all the required channels yet. Please join the remaining channels and try again:",
            reply_markup=reply_markup
        )

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id

    # Generate referral link
    referral_link = f"https://t.me/hhamarathonbot?start={user_id}"

    welcome_message = (
        f"Hello {query.from_user.first_name if query else update.effective_user.first_name}! "
        f"Congratulations on your first step towards a bright future!🥳\n\n"
        f"Now, invite your friends to get your link to our private channel where we have lessons together.👨🏻‍💻👩‍💻\n\n"
        f"Your referral link 🔗: {referral_link}"
    )

    keyboard = [
        [InlineKeyboardButton("👤 Profile", callback_data='profile'),
         InlineKeyboardButton("🔗 Referral Link", callback_data='referral_link')],
        [InlineKeyboardButton("✉️ Invite Friends", switch_inline_query=("""
🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉
Congratulations on your first step towards a bright future!
Now, invite your friends to get your link to our private channel where we have lessons together.
""" + referral_link))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if query:
        await query.edit_message_text(welcome_message, reply_markup=reply_markup)
    else:
        await update.message.reply_text(welcome_message, reply_markup=reply_markup)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except BadRequest as e:
        if "Query is too old" in str(e):
            logger.warning("Received an expired callback query. Proceeding without answering.")
        else:
            raise

    if query.data == 'check_subscription':
        await check_subscription(update, context)
    elif query.data == 'profile':
        await show_profile(update, context)
    elif query.data == 'referral_link':
        await show_referral_link(update, context)
    elif query.data == 'back_to_main':
        await show_main_menu(update, context)

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    c.execute("SELECT invited_count, channels_followed FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    if result:
        invited_count, channels_followed = result
        remaining = max(0, REQUIRED_INVITES - invited_count)

        if channels_followed:
            profile_message = (
                f"Name: {query.from_user.first_name}\n"
                f"Invited friends: {invited_count}\n"
            )
            
            if invited_count >= REQUIRED_INVITES:
                profile_message += f"""
                \n🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉
Congratulations! You can join the channel via this link:
{CHANNEL_LINK}"""
            else:
                profile_message += f"\n⌛️⏳Friends to invite for channel access: {remaining}"
        else:
            profile_message = "❌Please follow the required channels first."
        
        keyboard = [[InlineKeyboardButton("Back", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await query.edit_message_text(text=profile_message, reply_markup=reply_markup)
        except BadRequest as e:
            if "Message is not modified" in str(e):
                pass
            else:
                raise
    else:
        await query.edit_message_text(text="User not found. Please start the bot again.")

async def show_referral_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    c.execute("SELECT channels_followed FROM users WHERE user_id = ?", (user_id,))
    channels_followed = c.fetchone()[0]
    
    if channels_followed:
        referral_link = f"""
🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉
Congratulations on your first step towards a bright future!
Now, invite your friends to get your link to our private channel where we have lessons together.
https://t.me/hhamarathonbot?start={user_id}"""
        keyboard = [
            [InlineKeyboardButton("Invite Friends", switch_inline_query=(referral_link + """🎉🎉🎉🎉Congratulations on your first step towards a bright future!
        Now, invite your friends to get your link to our private channel where we have lessons together."""))],
            [InlineKeyboardButton("Back", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.edit_message_text(text=f"Your referral link 🔗: {referral_link}", reply_markup=reply_markup)
        except BadRequest as e:
            if "Message is not modified" in str(e):
                pass
            else:
                raise
    else:
        await query.edit_message_text(text="❌ Please follow the required channels first to get your referral link.")

async def check_invites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    c.execute("SELECT invited_count, channels_followed FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    
    if result:
        invited_count, channels_followed = result
        if channels_followed:
            if invited_count >= REQUIRED_INVITES:
                await update.message.reply_text(
                    f"📣 You have successfully invited {REQUIRED_INVITES} friends. "
                    f"Now you can join the channel via this link 🔗: {CHANNEL_LINK}"
                )
            else:
                remaining = REQUIRED_INVITES - invited_count
                await update.message.reply_text(f"You need to invite {remaining} more friends to get access to the channel.")
        else:
            await update.message.reply_text("❌ Please follow the required channels first.")
    else:
        await update.message.reply_text("User not found. Please start the bot again.")

def main():
    application = ApplicationBuilder().token('7134702100:AAEzbSQhcRvZ4Q8DYt8hguoFKAlRox_qYc4').build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(CommandHandler("check", check_invites))

    application.run_polling()

if __name__ == '__main__':
    main()