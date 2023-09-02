import telebot
import pika
import configparser
import datetime
import i18n
import logging.handlers
from telebot import types

config = configparser.ConfigParser()
config.read('bot.conf')
TOKEN = config['TELEGRAM']['BOT_TOKEN']
RABBITCONNECT = config['RABBITMQ']['CONNECTION_STRING']
BANNED = config['TELEGRAM']['BAN']

logger_info = logging.getLogger('VideoCaptionsBot')
logger_info.setLevel(logging.DEBUG)
handler_info = logging.handlers.TimedRotatingFileHandler(
    '/var/log/VideoCaptionsBot/videocaptionsbot.log',
    when='midnight',
    interval=1,
    backupCount=30,
    encoding='utf-8'
)
logger_info.addHandler(handler_info)

bot = telebot.TeleBot(TOKEN)

def add_log(message):
    logger_info.info(
        f'{datetime.datetime.now()} {message}'
    )

def get_text(message, arg):
    i18n.load_path.append("i18n")
    i18n.set("fallback", "en-us")
    user_lang = message.from_user.language_code.lower()
    return i18n.t(arg, locale=user_lang)

def set_menu(message):
    try:
        bot.set_my_commands(
            [
                telebot.types.BotCommand(
                    get_text(message, 'bot.menu_start'),
                    get_text(message, 'bot.menu_start_description')
                ),
                telebot.types.BotCommand(
                    get_text(message, 'bot.menu_tos'),
                    get_text(message, 'bot.menu_tos_description')
                ),
                telebot.types.BotCommand(
                    get_text(message, 'bot.menu_donate'),
                    get_text(message, 'bot.menu_donate_description')
                ),
                telebot.types.BotCommand(
                    get_text(message, 'bot.menu_info'),
                    get_text(message, 'bot.menu_info_description')
                )
            ], scope=types.BotCommandScopeChat(message.from_user.id)
        )
    except:
        pass

def add_to_line(message):
    rabbitmq_con = pika.BlockingConnection(pika.URLParameters(RABBITCONNECT))
    rabbit = rabbitmq_con.channel()
    rabbit.queue_declare(queue='VideoCaptionsBot', durable=True)
    rabbit.basic_publish(
        exchange='',
        routing_key='VideoCaptionsBot',
        body=str(message),
        properties=pika.BasicProperties(
            delivery_mode = pika.spec.PERSISTENT_DELIVERY_MODE
        )
    )
    rabbitmq_con.close()

@bot.message_handler(commands=["start"])
def cmd_start(message):
    add_log(message)
    set_menu(message)
    bot.send_chat_action(message.chat.id, 'typing')
    bot.send_message(
        message.from_user.id,
        get_text(message, 'bot.cmd_start'),
        parse_mode='HTML'
    )
    bot.send_message(
        message.from_user.id,
        get_text(message, 'bot.cmd_tos'),
        parse_mode='HTML',
        disable_web_page_preview=True
    )

@bot.message_handler(commands=["info"])
def cmd_info(message):
    add_log(message)
    set_menu(message)
    bot.send_chat_action(message.chat.id, 'typing')
    bot.send_message(
        message.from_user.id,
        get_text(message, 'bot.cmd_info'),
        parse_mode='HTML',
        disable_web_page_preview=True
    )

@bot.message_handler(commands=["pix", "donate"])
def cmd_donate(message):
    add_log(message)
    set_menu(message)
    bot.send_chat_action(message.chat.id, 'typing')
    bot.send_message(
        message.from_user.id,
        get_text(message, 'bot.cmd_donate'),
        parse_mode='HTML',
        disable_web_page_preview=True
    )

@bot.message_handler(commands=["tos"])
def cmd_tos(message):
    add_log(message)
    set_menu(message)
    bot.send_chat_action(message.chat.id, 'typing')
    bot.send_message(
        message.from_user.id,
        get_text(message, 'bot.cmd_tos'),
        parse_mode='HTML',
        disable_web_page_preview=True
    )

@bot.message_handler(content_types=['video', 'document', 'video_note'])
def get_video(message):
    add_log(message)
    if str(message.from_user.id) in BANNED:
        bot.delete_message(message.from_user.id, message.message_id)
        return 0
    bot.send_message(
        message.from_user.id,
        get_text(message, 'bot.please_wait'),
        reply_to_message_id=message.id
    )
    add_to_line(message)

if __name__ == "__main__":
    bot.infinity_polling()
