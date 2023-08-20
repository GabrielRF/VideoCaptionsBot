import telebot
import pika
import configparser

config = configparser.ConfigParser()
config.read('bot.conf')
TOKEN = config['TELEGRAM']['BOT_TOKEN']
RABBITCONNECT = config['RABBITMQ']['CONNECTION_STRING']

bot = telebot.TeleBot(TOKEN)

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
def start(message):
    bot.send_chat_action(message.chat.id, 'typing')
    print(message.from_user)
    bot.send_message(
        message.from_user.id,
        'Olá! Me envie um vídeo e irei criar as legendas automaticamente.',
        parse_mode='HTML'
    )

@bot.message_handler(content_types=['video', 'document', 'video_note'])
def get_video(message):
    add_to_line(message)
    bot.send_message(message.from_user.id, '⏳ Por favor, aguarde.')

if __name__ == "__main__":
    bot.infinity_polling()
