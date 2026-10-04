# child-diary-downloader

[![CI](https://github.com/fredericofernandes/child-diary-downloader/actions/workflows/ci.yml/badge.svg)](https://github.com/fredericofernandes/child-diary-downloader/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/fredericofernandes/child-diary-downloader?display_name=tag)](https://github.com/fredericofernandes/child-diary-downloader/releases)
[![Docker](https://img.shields.io/badge/ghcr.io-child--diary--downloader-blue?logo=docker)](https://github.com/fredericofernandes/child-diary-downloader/pkgs/container/child-diary-downloader)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue?logo=python&logoColor=white)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Backup automático do diário dos teus filhos na app [ChildDiary](https://childdiary.net),
com resumos diários no Telegram.** Ferramenta não oficial, feita por um pai, para
famílias em Portugal e na Irlanda.

🇬🇧 [English version](README.en.md)

<p align="center">
  <img src="docs/images/telegram-demo.svg" alt="Exemplo de resumo diário no Telegram (dados fictícios)" width="380">
</p>

## Porquê

As creches e jardins de infância que usam o ChildDiary publicam todos os dias
fotos, vídeos, relatórios e a rotina de cada criança: o que comeu, quanto
dormiu, o que fez. São as memórias dos primeiros anos dos nossos filhos, e
**ficam num serviço que não controlamos**. Quando a criança muda de escola ou
termina o pré-escolar, o acesso pode acabar e os anos de fotografias com ele.

Este projecto descarrega tudo para uma pasta tua, organizada por criança e por
dia, com as datas gravadas nas próprias fotos para que o Apple Photos, o
Google Photos ou o Immich as mostrem no sítio certo da linha do tempo. E, como
bónus, envia-te a rotina do dia para o Telegram assim que a educadora a
publica.

Os [termos de serviço do ChildDiary](https://childdiary.net) reconhecem que os
dados das crianças pertencem aos encarregados de educação (RGPD) e não proíbem
o acesso automatizado à própria conta. Usa-o apenas na tua conta.

## O que faz

- **Arquiva tudo**: fotos, vídeos e PDFs de todas as entradas da tua conta, em
  `<arquivo>/<Criança>/<Ano>/<AAAA-MM-DD>/AAAA-MM-DD_HHMMSS_NN.jpg`.
- **Datas correctas**: data da entrada gravada no EXIF (fotos), nos metadados
  QuickTime (vídeos) e no `mtime` dos ficheiros, mais a legenda da publicação
  como descrição da foto.
- **Encaminha as publicações de sala e de escola** para a pasta da criança
  certa, com um mapa de routing que o `childdiary setup` propõe sozinho.
- **Documentos com nome legível**: relatórios de desenvolvimento, ementas
  adaptadas e circulares dirigidas à tua criança ganham uma cópia em
  `<Criança>/Documentos/AAAA-MM-DD — Título.pdf`.
- **Resumos no Telegram**: rotina diária (entrada e saída, refeições, sestas,
  higiene, actividades), publicações com fotos em álbum, eventos com data e
  pedido de confirmação. Em português ou em inglês.
- **Corre sozinho todos os dias**: Docker com agendamento interno e
  healthcheck, ou launchd, systemd e cron. Guarda o que já processou, retenta
  o que falhou e avisa-te no Telegram se algo correr mal.
- **Boa vizinhança**: identifica-se com um User-Agent honesto, espera entre
  pedidos e respeita os pedidos de abrandar do servidor. Contorna um defeito
  da paginação da API que perde uma entrada em cada fronteira de página.

Várias contas (uma por creche), várias crianças por conta, e irmãos em escolas
diferentes: tudo numa configuração.

```
~/Pictures/childdiary/
├── Maria/
│   ├── 2025/
│   │   └── 2025-09-15/
│   │       ├── 2025-09-15_101530_01.jpg
│   │       ├── 2025-09-15_101530_02.jpg
│   │       └── 2025-09-15_143012_01.mp4
│   └── Documentos/
│       ├── 2025-12-19 — Relatório de desenvolvimento 1.º período.pdf
│       └── Ementas/
│           └── 2026-01-05 — Ementa adaptada sem lactose.pdf
└── Tomás/
    └── 2026/
        └── 2026-03-10/
            └── 2026-03-10_091500_01.jpg
```

## Instalação em 5 minutos (Docker)

Precisas de Docker num computador que fique ligado (um NAS, um Raspberry Pi,
um mini-PC) e de um bot do Telegram (opcional: sem ele, só arquiva).

```sh
mkdir -p childdiary/{config,data,archive} && cd childdiary
curl -O https://raw.githubusercontent.com/fredericofernandes/child-diary-downloader/main/compose.yaml
docker compose run --rm childdiary setup     # faz login, descobre as crianças e salas, escreve a config
docker compose run --rm childdiary check     # confirma logins, Telegram e pasta do arquivo
docker compose run --rm childdiary run --no-telegram   # primeira carga completa, sem notificações
docker compose up -d                          # daí em diante, todos os dias às 19:00
```

Guia completo, incluindo NAS Synology/QNAP/Unraid e Raspberry Pi:
[docs/install-docker.md](docs/install-docker.md) e [docs/install-nas.md](docs/install-nas.md).

Sem Docker (Mac ou Linux com `uv`/`pipx`, agendado com launchd, systemd ou
cron): [docs/install-python.md](docs/install-python.md).

## Configuração

O `childdiary setup` escreve dois ficheiros:

- `config.yaml`: crianças, salas, língua, pastas. Sem segredos.
- `.env`: passwords e token do Telegram, referidos no YAML como `${NOME}`.

Um exemplo comentado com todas as opções está em
[`config.example.yaml`](config.example.yaml); a referência completa em
[docs/configuration.md](docs/configuration.md).

```yaml
language: pt                 # ou en
timezone: Europe/Lisbon      # ou Europe/Dublin
accounts:
  - name: Creche Exemplo
    username: familia.exemplo@example.com
    password: ${CDD_PASSWORD_CRECHE}
    children:
      "00000000-0000-0000-0000-000000000001": Maria
routing:
  groups:
    "Sala Girassóis": [Maria]
telegram:
  token: ${CDD_TELEGRAM_TOKEN}
  chat_id: ${CDD_TELEGRAM_CHAT_ID}
```

### Comandos

| Comando | Para quê |
|---|---|
| `childdiary setup` | assistente de primeira configuração |
| `childdiary check [--send-test]` | valida logins, IDs das crianças, Telegram, exiftool |
| `childdiary run` | descarrega o que é novo, arquiva e notifica |
| `childdiary run --no-telegram` | só arquiva (primeira carga, reprocessamento) |
| `childdiary run --dry-run` | mostra o que faria, sem tocar em nada |
| `childdiary run --since AAAA-MM-DD` | volta a processar as entradas desde essa data (ficheiros existentes ficam) |
| `childdiary list-groups` | lista crianças e salas de cada conta, com IDs |
| `childdiary status` | entradas processadas, falhas pendentes, ficheiros arquivados |
| `childdiary verify [--hash]` | confere o arquivo com o estado: ficheiros em falta ou alterados |
| `childdiary daemon` | fica a correr e executa à hora agendada (Docker) |
| `childdiary health` | estado do daemon, para o healthcheck do Docker |

## Perguntas frequentes

**Isto é oficial?** Não. É um projecto independente que usa a mesma API que a
aplicação web do ChildDiary. Pode deixar de funcionar se a API mudar; abre uma
issue se isso acontecer.

**É seguro dar-lhe a minha password?** A password fica só na tua máquina, num
ficheiro `.env` com permissões restritas, e é usada apenas para fazer login em
`app.childdiary.net`. O código é público e pequeno: lê-o.

**Porque não corre no GitHub Actions, de graça, a cada dia?** Porque isso
significava pôr as tuas credenciais e as fotos dos teus filhos em servidores
de terceiros, sem estado persistente e sem garantia de hora. Fotos de crianças
ficam em casa: um NAS, um Raspberry Pi ou o teu portátil.

**Apareceu uma sala nova e as fotos foram para uma pasta com o nome da sala.**
É o comportamento previsto: adiciona a sala a `routing.groups` no
`config.yaml` e move a pasta. O log avisa sempre que isso acontece.

**Posso re-descarregar tudo?** Apaga o `state.db` da pasta de dados e corre
`childdiary run --no-telegram`. Ficheiros já existentes não são descarregados
outra vez. `childdiary status` mostra o que o estado conhece.

**E as fotos que a escola apagou?** Se o ficheiro já não existe no servidor
(404), é registado no log e a entrada é dada como feita. O que já estava no
teu arquivo fica.

**Funciona na Irlanda?** Sim. Usa `language: en` e `timezone: Europe/Dublin`.

**Preciso do exiftool?** Não, mas sem ele as fotos ficam só com o `mtime`
correcto e as apps de fotos usam a data de importação. A imagem Docker já o
inclui.

## Roadmap

- [ ] Mais notificadores: email, ntfy, Discord, Slack (via apprise)
- [ ] Resumo diário único em vez de uma mensagem por entrada
- [ ] Estado em SQLite e modelo de dados tipado para as entradas
- [ ] Exportação directa para Immich e Apple Photos
- [ ] PDF anual por criança (o "livro do ano")
- [ ] Interface web mínima para navegar o arquivo

Ideias e pedidos nas [issues](https://github.com/fredericofernandes/child-diary-downloader/issues).

## Contribuir

Correcções, traduções e relatos de escolas com estruturas diferentes são
bem-vindos. Lê o [CONTRIBUTING.md](CONTRIBUTING.md): o projecto tem testes com
dados fictícios, `ruff`, `mypy` e `pre-commit`, e não aceita nenhum dado real
de crianças no repositório.

## Aviso

Projecto independente, sem qualquer ligação à ChildDiary. Destina-se
exclusivamente a fazer cópia de segurança dos dados da tua própria conta, dos
quais és responsável enquanto encarregado de educação. Não redistribuas o que
descarregares: são dados pessoais de crianças, tuas e das outras famílias da
sala.

## Licença

[MIT](LICENSE) © Frederico Fernandes
