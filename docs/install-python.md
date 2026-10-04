# Instalação sem Docker (pipx/uv) e agendamento no sistema

Para quem prefere correr directamente no Mac ou em Linux.

## Instalar

Com [uv](https://docs.astral.sh/uv/) (recomendado) ou pipx:

```sh
uv tool install git+https://github.com/fredericofernandes/child-diary-downloader
# ou
pipx install git+https://github.com/fredericofernandes/child-diary-downloader
```

E o `exiftool` (opcional, mas recomendado para as datas EXIF):

```sh
brew install exiftool            # macOS
sudo apt install libimage-exiftool-perl   # Debian/Ubuntu
```

## Configurar

A configuração vive na pasta de configuração do sistema:

| Sistema | `config.yaml` e `.env` | estado, logs |
|---|---|---|
| macOS | `~/Library/Application Support/childdiary-downloader/` | a mesma pasta |
| Linux | `~/.config/childdiary-downloader/` | `~/.local/share/childdiary-downloader/` |

```sh
childdiary --help
mkdir -p "~/Library/Application Support/childdiary-downloader"   # macOS
cp config.example.yaml "~/Library/Application Support/childdiary-downloader/config.yaml"
cp .env.example "~/Library/Application Support/childdiary-downloader/.env"
chmod 600 "~/Library/Application Support/childdiary-downloader/.env"
childdiary list-groups      # IDs das crianças e nomes das salas
childdiary run --no-notify   # primeira carga completa
```

`--config` e `--data-dir` (ou `CDD_CONFIG`, `CDD_DATA_DIR`) mudam estes caminhos.

## Agendar

### macOS: launchd

Guarda como `~/Library/LaunchAgents/net.childdiary.downloader.plist`,
substituindo `/Users/NOME` e o caminho do executável (`which childdiary`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>net.childdiary.downloader</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/NOME/.local/bin/childdiary</string>
        <string>run</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>19</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/NOME/Library/Application Support/childdiary-downloader/logs/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/NOME/Library/Application Support/childdiary-downloader/logs/launchd.log</string>
</dict>
</plist>
```

```sh
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/net.childdiary.downloader.plist   # activar
launchctl kickstart gui/$UID/net.childdiary.downloader                                # correr já
launchctl bootout gui/$UID/net.childdiary.downloader                                  # desactivar
```

Se o Mac estiver a dormir às 19:00, o launchd corre o job quando acordar.

### Linux: systemd timer

`~/.config/systemd/user/childdiary.service`:

```ini
[Unit]
Description=ChildDiary backup

[Service]
Type=oneshot
ExecStart=%h/.local/bin/childdiary run
```

`~/.config/systemd/user/childdiary.timer`:

```ini
[Unit]
Description=Run the ChildDiary backup daily

[Timer]
OnCalendar=*-*-* 19:00:00
Persistent=true
RandomizedDelaySec=5m

[Install]
WantedBy=timers.target
```

```sh
systemctl --user daemon-reload
systemctl --user enable --now childdiary.timer
systemctl --user list-timers            # confirmar
loginctl enable-linger $USER            # correr mesmo sem sessão aberta
```

### cron

```cron
0 19 * * * /home/NOME/.local/bin/childdiary run >> /home/NOME/.local/share/childdiary-downloader/logs/cron.log 2>&1
```

## Daemon interno (alternativa a tudo o resto)

`childdiary daemon --schedule "0 19 * * *"` fica a correr e executa à hora
indicada; é o que a imagem Docker usa. Serve para quem prefere um único
processo supervisionado (por exemplo com `systemd` tipo `simple`).
