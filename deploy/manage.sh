#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
COMPOSE_FILE="${SCRIPT_DIR}/compose.yaml"
ENV_FILE="${TELEGRAM_BOT_ENV_FILE:-${SCRIPT_DIR}/.env}"

usage() {
  echo "Usage: $0 {build|start|stop|restart|status|logs}"
}

if [ "$#" -ne 1 ]; then
  usage
  exit 2
fi

if [ ! -f "${ENV_FILE}" ]; then
  echo "Missing runtime environment file: ${ENV_FILE}" >&2
  echo "Copy ${SCRIPT_DIR}/.env.example to ${SCRIPT_DIR}/.env and fill required values." >&2
  exit 2
fi

export TELEGRAM_BOT_ENV_FILE="${ENV_FILE}"

compose() {
  docker compose --project-directory "${SCRIPT_DIR}" -f "${COMPOSE_FILE}" "$@"
}

case "$1" in
  build)
    compose build
    ;;
  start)
    compose up --detach --build
    ;;
  stop)
    compose down
    ;;
  restart)
    compose down
    compose up --detach --build
    ;;
  status)
    compose ps
    ;;
  logs)
    compose logs --follow --tail=200
    ;;
  *)
    usage
    exit 2
    ;;
esac
