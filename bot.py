import asyncio
import html
import json
import logging
from logging.handlers import RotatingFileHandler
import traceback
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, CallbackQueryHandler, Defaults, filters
from warnings import filterwarnings
from telegram.warnings import PTBUserWarning
import configparser
import qbittorrentapi

# Enable logging
logging.basicConfig(
        handlers=[RotatingFileHandler('logs/bot_debug.log', maxBytes=4*1024*1024, backupCount=5)],
        level=logging.DEBUG,
        format="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
        datefmt='%Y-%m-%d %H:%M:%S')

logger = logging.getLogger(__name__)

config = configparser.ConfigParser()

try:
    config.read("config.ini")
    tgbot = config["tgbot"]
    qbittorrent_web = config["qbittorrent_web"]
except:
    config.add_section("tgbot")
    config.set("tgbot", "BOT_TOKEN", "5855984510:AAHNxCAxhgy7b8CuRKSIlJqYXrJG1Tweck0")
    config.set("tgbot", "BOT_USERNAME", "testbot")
    config.set("tgbot", "DEVELOPER_CHAT_ID", "4759422")
    config.add_section("qbittorrent_web")
    config.set("qbittorrent_web", "host", "localhost")
    config.set("qbittorrent_web", "port", "8080")
    config.set("qbittorrent_web", "username", "admin")
    config.set("qbittorrent_web", "password", "adminadmin")

    with open("config.ini", 'w') as sett:
        config.write(sett)

BOT_TOKEN = tgbot['BOT_TOKEN']
BOT_ID = int(tgbot['BOT_TOKEN'][:10])
BOT_USERNAME = tgbot['BOT_USERNAME']
DEVELOPER_CHAT_ID = tgbot['DEVELOPER_CHAT_ID'] #Sends error messages to the developer

# instantiate a Client using the appropriate WebUI configuration
conn_info = dict(
    host=qbittorrent_web['host'],
    port=qbittorrent_web['port'],
    username=qbittorrent_web['username'],
    password=qbittorrent_web['password'],
)
qbt_client = qbittorrentapi.Client(**conn_info)

try:
    qbt_client.auth_log_in()
except qbittorrentapi.LoginFailed as e:
    print(e)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    # Log the error before we do anything else, so we can see it even if something breaks.
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    # Build the message with some markup and additional information about what happened.
    # You might need to add some logic to deal with messages longer than the 4096 character limit.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
#        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
#        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    # Finally, send the message
    await context.bot.send_message(
        chat_id=DEVELOPER_CHAT_ID, text=message, parse_mode=ParseMode.HTML
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        query = update.callback_query
        await query.answer('✅')
        edit = 1
    except:
        edit = 0
    keyboard = [
        [
            InlineKeyboardButton(f"This Bot is on GitHub!", callback_data='/about'),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = f"Hello, welcome to Torrent Info Bot ℹ️\n\nJust send an hash to get some other info"
    if edit == 1:
        await query.edit_message_text(msg, reply_markup=reply_markup)
    elif edit == 0 or edit == 2:
        await context.bot.sendMessage(update.effective_user.id, msg, reply_markup=reply_markup)

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer('✅')
    keyboard = [
        [
            InlineKeyboardButton(f"Back 🔙", callback_data='/start'),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = f"This bot is made by <a href=\"https://github.com/BrandoDev\">BrandoDev</a> and you can clone your own from <a href=\"https://github.com/BrandoDev/torrent_info_bot\">GitHub</a>"
    await query.edit_message_text(msg, reply_markup=reply_markup)

async def qbit_fetch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global qbt_client
    hash = update.message.text
    magnet = f"magnet:?xt=urn:btih:{hash}"
    add = qbt_client.torrents_add(urls=magnet)
    if add == 'Fails.':
        delete = 0
    else:
        delete = 1
    await context.bot.sendMessage(update.effective_user.id, f"Please wait... Getting metadata")
    await asyncio.sleep(5)
    try:
        for attempt in range(15):
            try:
                export_bytes = qbt_client.torrents_export(hash)
            except:
                await asyncio.sleep(5)
                export_bytes = qbt_client.torrents_export(hash)
            else:
                break
    except:
        msg = f"Unable to get metadata, torrent is dead"
        await context.bot.sendMessage(update.effective_user.id, msg)
        if delete == 1:
            qbt_client.torrents_delete(torrent_hashes=[hash], delete_files=True) #deletes torrent after getting data
        return

    await asyncio.sleep(10)
    torrent_raw = qbt_client.torrents_info(torrent_hashes=hash)
    print(torrent_raw)
    torrent_name = torrent_raw[0].name
    magnet = torrent_raw[0].magnet_uri
    torrent_dowloaded_times = torrent_raw[0].completed
    torrent_size = round(int(torrent_raw[0].total_size) / 1.074e+9, 2) #converts Byte to GiB and round it to the second decimal
    torrent_seeder = torrent_raw[0].num_seeds
    torrent_leecher = torrent_raw[0].num_leechs

    with open(f"files/{torrent_name}.torrent", 'wb') as w:
        w.write(export_bytes)

    msg = f"Torrent name: {torrent_name}\n\nDownloaded: {torrent_dowloaded_times} times\nTorrent size: {torrent_size} GiB\n\nSeeder: Approx. {torrent_seeder}\nLeecher: Approx. {torrent_leecher}\n\nMagnet: <code>{magnet}</code>"
    await context.bot.sendDocument(update.effective_user.id, f"files/{torrent_name}.torrent", msg)
    if delete == 1:
        qbt_client.torrents_delete(torrent_hashes=[hash], delete_files=True) #deletes torrent after getting data

def main() -> None:
    # Create the Application and pass it your bot's token.
    defaults = Defaults(parse_mode=ParseMode.HTML)
    app = (Application.builder().token(BOT_TOKEN).defaults(defaults).build())
    filterwarnings(action='ignore', message=r".*CallbackQueryHandler", category=PTBUserWarning)

    # Start and info...
    app.add_handler(CommandHandler('start', start), 4)
    app.add_handler(CallbackQueryHandler(start, pattern='/start'), 4)
    app.add_handler(CallbackQueryHandler(about, pattern='/about'), 3)

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, qbit_fetch), 3)

    # ...and the error handler
    app.add_error_handler(error_handler)

    # Run the bot until the user presses Ctrl-C
    app.run_polling()


if __name__ == "__main__":
    main()
