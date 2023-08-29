import videocaptionsbot
import pika
import ffmpeg
import telebot
import i18n
import openai
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
MAX_TOKENS = int(config['OPENAI']['MAX_TOKENS'])

bot = telebot.TeleBot(TOKEN)

def get_text(message, arg):
    i18n.load_path.append("i18n")
    i18n.set("fallback", "en-us")
    user_lang = message['from_user']['language_code'].lower()
    return i18n.t(arg, locale=user_lang)

def subs_data(video_data):
    try:
        if video_data["width"] > video_data["height"]:
            subs_size = '20%'
            subs_marginv = video_data["height"]*0.07
        elif video_data["width"] == video_data["height"]:
            subs_size = '20%'
            subs_marginv = video_data["height"]*0.3
        else:
            subs_size = '10%'
            subs_marginv = video_data["height"]*0.02
    except:
        subs_size = '20%'
        subs_marginv =100
    return subs_size, subs_marginv

def add_subtitles(file_name, translate=False):
    if not translate:
        subtitle = f'{file_name}.srt'
        video_out = f'VideoCaptionsBot.{file_name}'
    else:
        subtitle = f'{file_name}_translated.srt'
        video_out = f'VideoCaptionsBot_translated.{file_name}'
    video = ffmpeg.input(file_name)
    video_data = ffmpeg.probe(file_name)['streams'][0]
    subs_size, subs_marginv = subs_data(video_data)
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
    return video_out, video_data["height"], video_data["width"]

def remove_files(file_name):
    names = [
        f'{file_name}.srt',
        f'{file_name}',
        f'VideoCaptionsBot.{file_name}',
        f'{file_name}_translated.srt',
        f'VideoCaptionsBot_translated.{file_name}'
    ]
    for fname in names:
        try:
            os.remove(fname)
        except:
            pass

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

def send_file(user, file_name, content_type='document', caption=None, height=None, width=None):
    document = open(file_name, 'rb')
    if content_type == 'video_note':
        bot.send_video_note(user, document)
    elif content_type == 'video':
        bot.send_video(user, document, caption=caption, width=width, height=height)
    else:
        bot.send_document(user, document, caption=caption)

def should_translate(transcription, message):
    user_lang = message['from_user']['language_code'].lower()
    transcription_lang = transcription['language']
    if transcription_lang in user_lang:
        return False
    return True

def translate_srt_file(file_name, message):
    user_lang = message['from_user']['language_code'].lower()
    openai.api_key = config['OPENAI']['SECRETKEY']
    gpt_query = []
    content = open(f'{file_name}.srt', 'r').read()
    gpt_query.append(
        {
            'role': 'user',
            'content': f'Translate the srt file to {user_lang} keeping timestamps.\n{content}'
        }
    )
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages = gpt_query,
        n = 1,
        temperature = 1,
        max_tokens=MAX_TOKENS
    )

    text = response.choices[0].message.content
    tokens = response.usage.total_tokens
    return text, tokens

def save_translated_srt(content, file_name):
    translated_srt = open(f'{file_name}_translated.srt', 'w')
    translated_srt.write(content)
    translated_srt.close()

def check_policy(transcription, user_id):
    openai.api_key = config['OPENAI']['SECRETKEY']
    response = openai.Moderation.create(
        input = transcription['text']
    )
    print(response)
    videocaptionsbot.add_log(f'{user_id}: \n{response}')
    return response['results'][0]['flagged']

def consume_line(rbt, method, properties, message):
    rbt.basic_ack(delivery_tag=method.delivery_tag)
    message = yaml.safe_load(message)
    msg = bot.send_message(
        message['from_user']['id'],
        get_text(message, 'bot.downloading'),
        reply_to_message_id=message['message_id']
    ) 
    try:
        file_name = download_file(message)
        bot.edit_message_text(
            get_text(message, 'bot.generating_subtitles'),
            msg.chat.id, msg.id
        )
        transcription = voice_to_text(file_name)
        if check_policy(transcription, message['from_user']['id']):
            bot.delete_message(message['from_user']['id'], message['message_id'])
            bot.edit_message_text(
                get_text(message, 'bot.restricted_content'),
                msg.chat.id, msg.id
            )
            remove_files(file_name)
            return
        create_subs(file_name, transcription)
        translated = should_translate(transcription, message)
        if translated:
            try:
                content, tokens = translate_srt_file(file_name, message)
                if tokens > MAX_TOKENS:
                    translated = False
                save_translated_srt(content, file_name)
            except:
                translated = False
                pass
    except Exception as e:
        bot.delete_message(msg.chat.id, msg.id)
        print(e)
        if 'file is too big' in str(e):
            exception = get_text(message, 'bot.error_file_too_big')
        elif 'string indices must be integers' in str(e):
            exception = get_text(message, 'bot.error_file_not_video')
        elif 'does not contain any stream' in str(e):
            exception = get_text(message, 'bot.error_file_not_video')
        else:
            exception = get_text(message, 'bot.error_unknown')
        bot.send_message(
            msg.chat.id,
            f'{get_text(message, "bot.error")}\n{exception}',
            reply_to_message_id=message['message_id'],
            parse_mode='HTML'
        )
        try:
            remove_files(file_name)
        except:
            pass
        return
    #send_file(msg.chat.id, f'{file_name}.srt')
    bot.edit_message_text(
        get_text(message, 'bot.adding_subtitles'),
        msg.chat.id, msg.id
    )
    try:
        video_with_captions, height, width = add_subtitles(file_name)
        bot.edit_message_text(
            get_text(message, 'bot.sending_file'),
            msg.chat.id, msg.id
        )
        send_file(
            msg.chat.id,
            video_with_captions,
            message['content_type'],
            caption=get_text(message, 'bot.original_video'),
            height=height,
            width=width
        )
        if translated:
            video_with_translated_captions, height, width = add_subtitles(file_name, True)
            send_file(
                msg.chat.id,
                video_with_translated_captions,
                message['content_type'],
                caption=get_text(message, 'bot.translated_video'),
                height=height,
                width=width
            )
    except Exception as e:
        exception = get_text(message, 'bot.error_file_too_big')
        bot.send_message(
            msg.chat.id,
            f'{get_text(message, "bot.error")}\n{exception}',
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
