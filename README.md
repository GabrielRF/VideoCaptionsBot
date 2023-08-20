# VideoCaptionsBot
> Em beta

## Contribuições

Toda contribuição é bem vinda!

* Verifique as issues abertas e, se possível, sugira soluções;
* Abra novas issues;
* Envie um PR (preferencialmente vinculado a uma issue);
* Fale comigo no Telegram ([@GabrielRF](https://t.me/GabrielRF)).

## Funcionamento

Este bot possui dois processos em execução em paralelo. São eles:

### VideoCaptionsBot.py

O arquivo `videocaptionsbot.py` faz o `polling` das atualizações. Assim que recebe um arquivo, um vídeo ou uma "mensagem de bolinha", a mensagem é enviada ao _RabbitMQ_.

#### Funções

* `add_to_line`: Adiciona a mensagem recebida à fila;
* `start`: Responde o comando `/start`;
* `get_video`: Responde ao receber um vídeo, um arquivo ou uma "mensagem de bolinha".

### Consumeline.py

Ao perceber alguma mensagem na fila do _RabbitMQ_, este arquivo inicia o processamento da mensagem.

#### Funções

* `subs_data`: Verifica os valores de tamanho da legenda e altura em relação ao vídeo;
* `add_subtitles`: Adiciona as legendas com base no arquivo `srt`;
* `remove_files`: Remove os arquivos do sistema;
* `download_file`: Baixa o arquivo do servidor do Telegram;
* `create_subs`: Cria o arquivo `.srt` com base na transcrição;
* `voice_to_text`: Faz a transcrição do vídeo recebido;
* `send_file`: Envia o arquivo com legendas ao usuário;
* `consume_line`: Verifica se há arquivos na fila e dá início ao processamento da legenda.
