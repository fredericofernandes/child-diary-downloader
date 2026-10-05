# Security

## What this tool handles

- Your ChildDiary password and the credentials of your notification
  services (Telegram bot token, apprise URLs), read from a `.env` file
  (created with mode 600) or environment variables. They are used only to
  talk to `app.childdiary.net` and to the services you configure in
  `notifiers` (for example `api.telegram.org`, your ntfy server or your
  SMTP server).
- Photos, videos and documents of children, written to a folder you choose.

Nothing is sent anywhere else: without notifiers, only `app.childdiary.net` is contacted. There is no telemetry.

## Recommendations

- Run it on a machine you control. Do not run it on shared CI or a free cloud
  runner; see the README FAQ.
- Keep the archive on an encrypted disk or a NAS with access control, and back
  it up: that is the whole point.
- Rotate your ChildDiary password and bot token if you ever paste them
  somewhere by mistake (`.env` is in `.gitignore`, but copies spread).

## Reporting a vulnerability

Please do not open a public issue for security problems. Use GitHub's private
vulnerability reporting on this repository ("Report a vulnerability" under the
Security tab), or contact the maintainer through the email on the GitHub
profile. You will get an answer within a week.

Supported: the latest release. Older releases get no fixes.
