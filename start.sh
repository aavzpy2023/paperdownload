#!/usr/bin/env bash
# One-step launcher for Linux and macOS: installs Docker if needed, starts the app, opens the browser.
set -euo pipefail
cd "$(dirname "$0")"

URL="http://localhost:81"
OS="$(uname -s)"

say() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
ask() { local reply; read -r -p "$1 [y/N] " reply; [[ "$reply" =~ ^[Yy]$ ]]; }
die() { printf '\n\033[1;31mError:\033[0m %s\n' "$*" >&2; exit 1; }

install_docker() {
  if [[ "$OS" == "Darwin" ]]; then
    if command -v brew >/dev/null 2>&1 && ask "Docker is not installed. Install Docker Desktop with Homebrew?"; then
      brew install --cask docker
    else
      die "Install Docker Desktop from https://www.docker.com/products/docker-desktop/ , open it once, then run ./start.sh again."
    fi
  else
    ask "Docker is not installed. Install it now with Docker's official script (asks for your password)?" \
      || die "Install Docker from https://docs.docker.com/engine/install/ and run ./start.sh again."
    curl -fsSL https://get.docker.com | sudo sh
    sudo systemctl enable --now docker 2>/dev/null || true
    sudo usermod -aG docker "$USER" 2>/dev/null || true
  fi
}

command -v docker >/dev/null 2>&1 || install_docker

DOCKER=(docker)
if ! docker info >/dev/null 2>&1; then
  if [[ "$OS" == "Darwin" ]]; then
    say "Starting Docker Desktop (this can take a minute)..."
    open -a Docker
  elif docker info 2>&1 | grep -qi "permission denied"; then
    DOCKER=(sudo docker)
  else
    sudo systemctl start docker 2>/dev/null || true
  fi
  for _ in $(seq 1 60); do "${DOCKER[@]}" info >/dev/null 2>&1 && break || sleep 3; done
  "${DOCKER[@]}" info >/dev/null 2>&1 || die "Docker is installed but not running. Start it and run ./start.sh again."
fi

if "${DOCKER[@]}" compose version >/dev/null 2>&1; then
  COMPOSE=("${DOCKER[@]}" compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  die "Docker Compose is missing. Update Docker (https://docs.docker.com/compose/install/) and run ./start.sh again."
fi

# First run: create a private admin password instead of a well-known default.
NEW_PASSWORD=""
if [[ ! -f .env ]]; then
  NEW_PASSWORD="$( (openssl rand -base64 18 2>/dev/null || head -c 24 /dev/urandom | base64) | tr -dc 'A-Za-z0-9' | head -c 14)"
  printf 'PD_ADMIN_USER=admin\nPD_ADMIN_PASSWORD=%s\n' "$NEW_PASSWORD" > .env
fi

say "Building and starting Paper Downloader (the first time takes 5-10 minutes)..."
"${COMPOSE[@]}" up -d --build

say "Waiting for the app to answer at $URL ..."
for _ in $(seq 1 60); do
  curl -fs -o /dev/null "$URL" && break || sleep 2
done
curl -fs -o /dev/null "$URL" || die "The app did not start. See the logs with: ${COMPOSE[*]} logs"

say "Ready: $URL"
if [[ -n "$NEW_PASSWORD" ]]; then
  printf '\n  First login  ->  user: \033[1madmin\033[0m   password: \033[1m%s\033[0m\n  (saved in the .env file; you can change it later in Users)\n' "$NEW_PASSWORD"
fi

if [[ "$OS" == "Darwin" ]]; then open "$URL"; else xdg-open "$URL" >/dev/null 2>&1 || true; fi
