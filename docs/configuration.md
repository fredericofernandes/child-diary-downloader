# Referência da configuração

`config.yaml` é lido da pasta de configuração do sistema (ver
[install-python.md](install-python.md)), de `--config`, ou de `$CDD_CONFIG`.
Qualquer valor no formato `${NOME}` é substituído pela variável de ambiente
`NOME`, que também pode vir de um ficheiro `.env` ao lado do `config.yaml`.

| Chave | Tipo | Defeito | Descrição |
|---|---|---|---|
| `archive_dir` | caminho | `~/Pictures/Child-Diary` | Raiz do arquivo. `$CDD_ARCHIVE_DIR` sobrepõe-se (é o que a imagem Docker usa para `/archive`). |
| `language` | `pt` \| `en` | `pt` | Língua das notificações e dos nomes de pastas por defeito. |
| `timezone` | nome IANA | `Europe/Lisbon` | Fuso horário da escola. Os timestamps da API trazem "Z" mas são hora local da escola; usa-se para o corte de entradas antigas e para o agendamento do daemon. |
| `accounts` | lista | obrigatório | Uma entrada por login no ChildDiary. |
| `accounts[].name` | texto | `Account N` | Nome nos logs e nos alertas. |
| `accounts[].username` | texto | obrigatório | Email de login. |
| `accounts[].password` | texto | obrigatório | Normalmente `${CDD_PASSWORD_...}`. |
| `accounts[].children` | mapa id → nome | `{}` | ID da criança na API → nome da pasta. `childdiary list-groups` mostra os IDs. |
| `routing.groups` | mapa nome → lista | `{}` | Publicações de uma sala/actividade → pasta(s) de criança. Sem mapeamento, usa-se a sala descoberta nas entradas da criança; sem isso, uma pasta com o nome da sala (com aviso no log). |
| `routing.instances` | mapa nome → lista | `{}` | Publicações da escola inteira → pasta(s). |
| `routing.child_since` | mapa nome → data | `{}` | Ignora publicações de escola anteriores à entrada da criança (`AAAA-MM-DD`). Nunca deixa a lista vazia. |
| `max_age_days` | inteiro ≥ 0 | `3` | Entradas mais antigas do que isto são arquivadas sem notificar. `0` desliga o corte. |
| `notifiers` | lista | `[]` | Serviços que recebem as notificações ([notifiers.md](notifiers.md)). Sem nenhum, só arquiva. |
| `notifiers[].type` | `telegram` \| `apprise` | `apprise` | `telegram` é um atalho que gera o URL `tgram://`. |
| `notifiers[].token`, `.chat_id` | texto | obrigatório com `telegram` | Token do bot e ID do chat. |
| `notifiers[].url` | texto | obrigatório com `apprise` | URL do serviço, normalmente `${VARIAVEL}`. |
| `notifiers[].media` | booleano | `true` | Também recebe fotos, vídeos e PDFs. |
| `notifiers[].name` | texto | o tipo | Nome nos logs e no `check`. |
| `telegram` | mapa | ausente | Formato antigo (até 0.1): equivale a um `notifiers` do tipo `telegram`; `telegram.max_age_days` ainda é lido. |
| `documents.folder` | texto | `Documentos` / `Documents` | Subpasta de cada criança para PDFs dirigidos só a ela. |
| `documents.subfolders` | mapa nome → palavras | `{Ementas: [ementa]}` / `{Menus: [menu]}` | PDFs cujo título contém uma das palavras vão para essa subpasta. |
| `network.request_delay_seconds` | número ≥ 0 | `0.5` | Pausa mínima entre pedidos ao childdiary.net. |

## Variáveis de ambiente

| Variável | Efeito |
|---|---|
| `CDD_CONFIG` | caminho do `config.yaml` |
| `CDD_CONFIG_DIR` | pasta onde procurar `config.yaml` e `.env` |
| `CDD_DATA_DIR` | pasta de estado, lock, logs, heartbeat |
| `CDD_ARCHIVE_DIR` | sobrepõe-se a `archive_dir` |
| `CDD_SCHEDULE` | expressão cron para `childdiary daemon` (defeito `0 19 * * *`) |
| `CDD_TELEGRAM_TOKEN`, `CDD_TELEGRAM_CHAT_ID`, `CDD_PASSWORD_*` | o que o `config.yaml` referir com `${...}` |

## Ficheiros de runtime (pasta de dados)

| Ficheiro | Conteúdo |
|---|---|
| `state.db` | SQLite: entradas processadas (com data e hora), falhas com o erro, e ficheiros arquivados com tamanho e SHA-256. `childdiary status` resume-o. |
| `state.json.migrated` | o estado das versões anteriores a 0.2, já importado para `state.db` |
| `.lock` | evita execuções sobrepostas |
| `logs/childdiary.log` | log com rotação (5 MB × 5) |
| `heartbeat`, `last_run.json` | escritos pelo daemon, lidos por `childdiary health` |
| `discovery_dump.json` | saída de `childdiary discover` (contém dados reais: não partilhar) |

## Como as entradas são tratadas

| Tipo na API | O que é | Notificação | Arquivo |
|---|---|---|---|
| 1 | publicação com texto e fotos | texto, depois álbum | fotos/vídeos na pasta do dia |
| 2 | rotina diária | horário, refeições, sestas, higiene, actividades, ocorrências | fotos, se existirem |
| 3 | publicação "revista" com blocos | título e textos pela ordem dos blocos, depois álbum pela ordem dos blocos | idem |
| 5 | evento / convite | título, descrição, início, fim, pedido de confirmação, videochamada | PDFs anexos |
| outro | desconhecido | aviso para verificar os logs | o JSON completo fica no log |

Uma entrada dirigida a várias das tuas crianças é guardada na pasta de cada
uma (um download, depois cópias). Uma entrada dirigida **exclusivamente** às
tuas crianças (relatório, ementa adaptada, circular pessoal) é a única cujos
PDFs ganham a cópia em `Documentos/`; circulares de sala listam todas as
crianças e ficam só na pasta do dia.
