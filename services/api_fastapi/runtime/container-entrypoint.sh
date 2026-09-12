#!/bin/sh
set -eu

umask 077

if [ "${CLAMAV_HOST:-127.0.0.1}" != "127.0.0.1" ] && [ "${CLAMAV_HOST:-127.0.0.1}" != "localhost" ]; then
  echo "CLAMAV_HOST must resolve to the same-container loopback daemon" >&2
  exit 1
fi
if [ "${CLAMAV_PORT:-3310}" != "3310" ]; then
  echo "CLAMAV_PORT must match the private clamd listener" >&2
  exit 1
fi

mkdir -p /run/clamav /var/log/clamav /var/lib/clamav
chown -R clamav:clamav /run/clamav /var/log/clamav /var/lib/clamav

if ! find /var/lib/clamav -maxdepth 1 -type f \( -name 'daily.c*d' -o -name 'main.c*d' \) | grep -q .; then
  echo "Initializing ClamAV signatures"
  su -s /bin/sh clamav -c '/usr/bin/freshclam --stdout --config-file=/etc/clamav/freshclam-init.conf'
fi

exec /usr/bin/supervisord -n -c /etc/supervisor/supervisord.conf
