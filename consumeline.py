import pika
import ffmpeg
import telebot
import os
import yaml
import urllib
import whisper
import configparser
from datetime import timedelta

config = configparser.ConfigParser()
config.read('bot.conf')
TOKEN = config['TELEGRAM']['BOT_TOKEN']
RABBITCONNECT = config['RABBITMQ']['CONNECTION_STRING']

bot = telebot.TeleBot(TOKEN)

def add_subtitles(file_name):
    subtitle = f'{file_name}.srt'
    video_out = f'VideoCaptionsBot.{file_name}'
    video = ffmpeg.input(file_name)
    video_data = ffmpeg.probe(file_name)['streams'][0]
    if video_data["width"] > video_data["height"]:
        subs_size = '20%'
        subs_marginv = video_data["height"]*0.07
    elif video_data["width"] == video_data["height"]:
        subs_size = '20%'
        subs_marginv = video_data["height"]*0.3
    else:
        subs_size = '10%'
        subs_marginv = video_data["height"]*0.02
    audio = video.audio
    ffmpeg.concat(
        video.filter("subtitles",
            subtitle,
            force_style=(
                'Fontsize={},PrimaryColour=&H03fcff,MarginV={}'
            ).format(subs_size, subs_marginv)
        ),
        audio,
        v=1,
        a=1).output(video_out).run()
    return video_out

def remove_files(file_name):
    os.remove(f'{file_name}.srt')
    os.remove(file_name)
    os.remove(f'VideoCaptionsBot.{file_name}')

def download_file(message):
    file_info = bot.get_file(message[message['content_type']]['file_id'])
    file_url = ("https://api.telegram.org/file/bot"
        + TOKEN + "/"
        + file_info.file_path
    )
    file_name, headers = urllib.request.urlretrieve(
        file_url, f'{message["from_user"]["id"]}.{file_url.split(".")[-1]}'
    )
    return file_name

def create_subs(file_name, transcription):
    subtitle = []
    for segment in transcription['segments']:
        startTime = f"0{timedelta(seconds=int(segment['start']))},000"
        endTime = f"0{timedelta(seconds=int(segment['end']))},000"
        text = segment['text']
        segmentId = segment['id']+1
        segment = f"{segmentId}\n{startTime} --> {endTime}\n{text[1:]}\n\n"
        subtitle.append(segment)
        with open(f'{file_name}.srt', 'a+', encoding='utf-8') as srtFile:
            srtFile.write(segment)

def voice_to_text(voice_file):
    model = whisper.load_model("small")
    result = model.transcribe(
        voice_file,
        fp16=False,
    )
    return result

def send_file(user, file_name, content_type='document'):
    document = open(file_name, 'rb')
    if content_type == 'video_note':
        bot.send_video_note(user, document)
    elif content_type == 'video':
        bot.send_video(user, document)
    else:
        bot.send_document(user, document)

def consume_line(rbt, method, properties, message):
    rbt.basic_ack(delivery_tag=method.delivery_tag)
    message = yaml.safe_load(message)
    msg = bot.send_message(
        message['from_user']['id'],
        '📎 Baixando arquivo...',
        reply_to_message_id=message['message_id']
    ) 
    try:
        file_name = download_file(message)
        bot.edit_message_text('📝 Gerando legendas...', msg.chat.id, msg.id)
        transcription = voice_to_text(file_name)
        create_subs(file_name, transcription)
    except Exception as e:
        bot.delete_message(msg.chat.id, msg.id)
        if 'file is too big' in str(e):
            exception = 'Arquivo é maior que o permitido.'
        elif 'string indices must be integers' in str(e):
            exception = 'Arquivo não é um vídeo.'
        elif 'does not contain any stream' in str(e):
            exception = 'Arquivo não é um vídeo.'
        else:
            exception = 'Erro desconhecido.'
        bot.send_message(
            msg.chat.id,
            f'❌ Erro.\n<code>{exception}</code>',
            reply_to_message_id=message['message_id'],
            parse_mode='HTML'
        )
        return
    #send_file(msg.chat.id, f'{file_name}.srt')
    bot.edit_message_text('🎞 Adicionando legendas ao vídeo...', msg.chat.id, msg.id)
    video_with_captions = add_subtitles(file_name)
    bot.edit_message_text('🎉 Enviando arquivo. Aguarde.', msg.chat.id, msg.id)
    try:
        send_file(msg.chat.id, video_with_captions, message['content_type'])
    except Exception as e:
        exception = 'Arquivo muito grande para ser enviado.'
        bot.send_message(
            msg.chat.id,
            f'❌ Erro.\n\n<code>{exception}</code>',
            reply_to_message_id=message['message_id'],
            parse_mode='HTML'
        )
    bot.delete_message(msg.chat.id, msg.id)
    remove_files(file_name)

if __name__ == "__main__":
    bot = telebot.TeleBot(TOKEN)
    rabbitmq_con = pika.BlockingConnection(pika.URLParameters(RABBITCONNECT))
    rabbit = rabbitmq_con.channel()
    rabbit.basic_qos(prefetch_count=1)
    rabbit.basic_consume(queue='VideoCaptionsBot', on_message_callback=consume_line)
    rabbit.start_consuming()
