# Notificações: Telegram, ntfy, email, Discord e mais

As notificações passam pelo [apprise](https://github.com/caronc/apprise), que
fala com mais de cem serviços através de um URL. Configuras zero ou mais
serviços em `notifiers:` no `config.yaml`; sem nenhum, o programa só arquiva.

```yaml
max_age_days: 3            # entradas mais antigas são arquivadas em silêncio
notifiers:
  - type: telegram         # atalho para tgram://token/chat_id
    token: ${CDD_TELEGRAM_TOKEN}
    chat_id: ${CDD_TELEGRAM_CHAT_ID}
  - type: apprise          # qualquer serviço, pelo URL
    url: ${CDD_NTFY_URL}
    media: true            # false = só texto (bom para email)
    name: ntfy             # opcional, aparece nos logs e no `check`
```

Os URLs contêm segredos (tokens, passwords), por isso ficam no `.env` e o
YAML refere-os com `${NOME}`.

Cada entrada do diário vai para todos os serviços. Se um deles falhar, a
entrada fica marcada para repetir na execução seguinte (os ficheiros já
arquivados não são descarregados outra vez). `childdiary check --send-test`
envia uma mensagem de teste a cada serviço.

## Telegram

1. Fala com o [@BotFather](https://t.me/BotFather), `/newbot`, guarda o token.
2. Abre uma conversa com o bot (ou mete-o num grupo da família) e manda-lhe
   uma mensagem.
3. Descobre o `chat_id`: abre `https://api.telegram.org/bot<TOKEN>/getUpdates`
   no browser e procura `"chat":{"id":…}`. Grupos têm ID negativo.

O apprise agrupa as fotos e vídeos em álbuns de até 10, põe a data e o título
como legenda, envia PDFs como documento e respeita os limites de 10 MB por
foto e 50 MB por ficheiro. Ficheiros maiores ficam só no arquivo.

Opções úteis no URL, se preferires `type: apprise` em vez do atalho:
`tgram://token/chat_id/?silent=yes` (sem som), `?topic=123` (tópico de um
grupo), `?format=markdown`.

## ntfy (notificações push sem conta)

Instala a app [ntfy](https://ntfy.sh) no telemóvel, subscreve um tópico com um
nome difícil de adivinhar, e usa `ntfy://ntfy.sh/o-teu-topico`. Para um
servidor próprio: `ntfys://user:pass@ntfy.example.com/topico`. As fotos vão
como anexo (limite de 15 MB no ntfy.sh público).

## Email

`mailto://utilizador:password@gmail.com?to=familia@example.com`. No Gmail
usa uma *app password*. Com `media: false` recebes só o texto, o que costuma
ser o que se quer num email; com `media: true` as fotos vão em anexo.
Outros servidores: `mailtos://user:pass@smtp.example.com:465?from=…&to=…`.

## Discord, Slack, Matrix, Pushover, Signal, WhatsApp…

| Serviço | URL |
|---|---|
| Discord (webhook) | `discord://webhook_id/webhook_token` |
| Slack (webhook) | `slack://TokenA/TokenB/TokenC` |
| Matrix | `matrix://user:pass@matrix.org/#sala` |
| Pushover | `pover://user_key@app_token` |
| Signal (signal-cli REST) | `signal://host:8080/+351911111111/+351922222222` |
| Home Assistant | `hassio://host/accesstoken` |

A lista completa, com todas as opções, está na
[wiki do apprise](https://github.com/caronc/apprise/wiki).

## Um resumo por dia em vez de uma mensagem por entrada

`mode: digest` guarda tudo o que a execução produziu e envia uma única
mensagem no fim (mais um lote com as fotos, se `media: true`). Com a
execução diária às 19:00, é um resumo do dia. Ideal para email.

```yaml
notifiers:
  - type: telegram            # imediato: cada entrada assim que chega
    token: ${CDD_TELEGRAM_TOKEN}
    chat_id: ${CDD_TELEGRAM_CHAT_ID}
  - type: apprise             # um email por dia, só texto
    url: ${CDD_EMAIL_URL}
    media: false
    mode: digest
```

Resumos muito longos são divididos em várias mensagens, sempre entre
entradas, nunca a meio de uma.

## Vários serviços ao mesmo tempo

Sim: por exemplo Telegram com fotos para os pais e email só de texto para os
avós. Cada serviço decide o que recebe com `media:`.
