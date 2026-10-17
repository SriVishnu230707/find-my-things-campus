#!/bin/sh
set -eu
umask 077
test -d /backups
target="$(mktemp /backups/campus-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX.dump)"
trap 'rm -f "$target" "$target.tmp"' EXIT INT TERM
pg_dump --format=custom --no-owner --no-privileges --file="$target.tmp"
pg_restore --list "$target.tmp" >/dev/null
mv "$target.tmp" "$target"
trap - EXIT INT TERM
echo "Backup created and archive inspected. Copy it off-host and perform a restore drill."
