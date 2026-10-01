# child-diary-downloader

> **Pré-lançamento.** O projecto está a ser preparado para a versão 0.1.0. A
> documentação completa (instalação em 5 minutos, Docker, FAQ) chega com essa
> versão. [English version](README.en.md) coming with 0.1.0.

Ferramenta **não oficial** para famílias que usam a app [ChildDiary](https://childdiary.net)
(Portugal e Irlanda). Faz backup do diário dos teus filhos e avisa-te no Telegram:

- Descarrega todas as entradas da tua conta e arquiva fotos, vídeos e PDFs em
  `~/Pictures/Child-Diary/<Criança>/<Ano>/<Data>/`, com data EXIF e mtime
  correctos (importável para Apple Photos, Google Photos ou Immich com a
  cronologia certa).
- Encaminha posts de salas e da escola para a pasta da criança certa.
- Envia os resumos diários (refeições, sestas, higiene, actividades, eventos)
  para o Telegram.
- Corre todos os dias sozinho (Docker, launchd, systemd ou cron), com estado
  persistente, retries e alerta de falha.

## Porquê

A escola pode apagar tudo quando a criança sai. As memórias dos primeiros anos
dos teus filhos merecem uma cópia que seja tua. Os termos de serviço do
ChildDiary reconhecem que os dados das crianças pertencem aos encarregados de
educação (RGPD) e não proíbem o acesso automatizado à própria conta.

## Instalação

- **Docker** (recomendado, qualquer máquina ou NAS): [docs/install-docker.md](docs/install-docker.md)
  e [docs/install-nas.md](docs/install-nas.md). `docker compose up -d` e fica a correr todos os dias.
- **Python** com launchd, systemd ou cron: [docs/install-python.md](docs/install-python.md).

## Estado actual

```sh
uv sync
cp config.example.yaml config.yaml   # e .env.example -> .env
uv run childdiary --config config.yaml run
```

Comandos: `childdiary run [--no-telegram]`, `childdiary list-groups`,
`childdiary discover`. Segredos vivem em variáveis de ambiente ou num `.env`,
nunca no `config.yaml` nem no repositório.

Notificações e nomes de pastas em português por defeito (`language: pt`) ou em
inglês (`language: en`); fuso horário da escola configurável (`timezone`).
Os pedidos ao childdiary.net identificam-se com um User-Agent honesto e
respeitam uma pausa mínima entre si.

## Aviso

Projecto independente, sem qualquer ligação à ChildDiary. Usa-o apenas na tua
própria conta e não redistribuas os dados descarregados: são dados pessoais de
crianças.

## Licença

MIT. Ver [LICENSE](LICENSE).
