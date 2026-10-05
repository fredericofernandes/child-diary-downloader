# Instalação com Docker (recomendada)

Funciona em qualquer máquina com Docker: PC, Mac, Raspberry Pi, NAS. A imagem
inclui o `exiftool` e corre o download todos os dias à hora que escolheres.

## 1. Preparar as pastas

```sh
mkdir -p childdiary/{config,data,archive} && cd childdiary
curl -O https://raw.githubusercontent.com/fredericofernandes/child-diary-downloader/main/compose.yaml
curl -o config/config.yaml https://raw.githubusercontent.com/fredericofernandes/child-diary-downloader/main/config.example.yaml
curl -o config/.env https://raw.githubusercontent.com/fredericofernandes/child-diary-downloader/main/.env.example
```

- `config/` guarda a configuração e os segredos (montada só de leitura).
- `data/` guarda o estado (que entradas já foram processadas), os logs e o heartbeat.
- `archive/` recebe as fotos, vídeos e PDFs. Pode ser uma pasta num disco externo ou numa partilha de rede.

## 2. Configurar

1. `config/.env`: passwords das contas ChildDiary, token/chat do Telegram e URLs de
   outros serviços de notificação ([notifiers.md](notifiers.md)).
2. `config/config.yaml`: crianças, salas, língua. Para descobrir os IDs das
   crianças e os nomes das salas:

   ```sh
   docker compose run --rm childdiary list-groups
   ```

## 3. Arrancar

```sh
docker compose up -d
docker compose logs -f          # acompanhar
docker compose ps               # "healthy" quando o daemon está vivo
```

Para fazer o primeiro download completo sem inundar as notificações:

```sh
docker compose run --rm childdiary run --no-notify
```

## Hora da execução

`CDD_SCHEDULE` no `compose.yaml` é uma expressão cron interpretada no fuso
horário da escola (`timezone` no `config.yaml`). Exemplos:

| Expressão | Significado |
|---|---|
| `0 19 * * *` | todos os dias às 19:00 (defeito) |
| `30 18 * * 1-5` | dias úteis às 18:30 |
| `0 13,19 * * *` | duas vezes por dia |

## Permissões dos ficheiros

O processo corre como o utilizador `childdiary` (UID 1000). Se a pasta
`archive/` pertencer a outro utilizador no host, ou usa `user: "UID:GID"` no
`compose.yaml`, ou constrói a imagem com `--build-arg UID=... GID=...`.

## Actualizar

```sh
docker compose pull && docker compose up -d
```

As versões seguem [semver](https://semver.org); `:latest` aponta sempre para
a última release estável e `:0.1` para a última 0.1.x.
