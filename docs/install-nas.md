# NAS e Raspberry Pi

A imagem é publicada para `linux/amd64` e `linux/arm64`, por isso corre em
NAS Intel/AMD, nos Synology/QNAP com ARM64 e no Raspberry Pi 4/5 (64 bits).

## Synology (Container Manager)

1. Em **File Station** cria a pasta `docker/childdiary` com as subpastas
   `config`, `data` e `archive` (ou aponta `archive` para a tua pasta de
   fotos, por exemplo `/volume1/photo/childdiary`).
2. Copia para `config/` o `config.yaml` e o `.env` já preenchidos (ver
   [install-docker.md](install-docker.md)).
3. **Container Manager → Project → Create**: nome `childdiary`, caminho
   `docker/childdiary`, cola o conteúdo de [`compose.yaml`](../compose.yaml).
   Ajusta `user:` para o UID/GID do teu utilizador DSM (vê com `id` via SSH).
4. **Build** e depois **Start**. O estado "Healthy" aparece ao fim de um ou
   dois minutos.

Para a primeira carga completa sem Telegram, abre um terminal no contentor
(Container → Terminal) e corre `childdiary run --no-telegram`.

## QNAP (Container Station) e Unraid

O mesmo `compose.yaml` funciona no Container Station (Create → Application).
No Unraid, usa o template "Docker Compose Manager" ou adiciona o contentor à
mão com a imagem `ghcr.io/fredericofernandes/child-diary-downloader:latest`,
as três pastas montadas em `/config`, `/data` e `/archive`, e a variável
`CDD_SCHEDULE`.

## Raspberry Pi

```sh
sudo apt install docker.io docker-compose-v2
sudo usermod -aG docker $USER   # sair e voltar a entrar
```

Depois segue [install-docker.md](install-docker.md). Um Pi 4 com 2 GB chega
de sobra; o download diário demora segundos, a carga inicial de vários anos
de fotos pode demorar uma ou duas horas.

## Fotos num disco externo ou partilha

Monta a pasta no host como habitualmente e aponta o volume `archive` para lá.
Em partilhas SMB/NFS o `exiftool` continua a funcionar; só o `mtime` pode ser
ignorado por alguns servidores, o que não afecta as datas EXIF.
