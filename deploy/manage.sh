#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
COMPOSE_FILE="${SCRIPT_DIR}/compose.yaml"
ENV_FILE="${TELEGRAM_BOT_ENV_FILE:-${SCRIPT_DIR}/.env}"

usage() {
  echo "Usage: $0 {build|start|stop|restart|status|logs}"
  echo "       $0 persona-preflight <candidate-container-path> <digest> <report>"
  echo "       $0 persona-release <candidate-container-path> <digest> <report>"
  echo "       $0 {persona-smoke|persona-rollback}"
}

if [ "$#" -lt 1 ]; then
  usage
  exit 2
fi

if [ ! -f "${ENV_FILE}" ]; then
  echo "Missing runtime environment file: ${ENV_FILE}" >&2
  echo "Copy ${SCRIPT_DIR}/.env.example to ${SCRIPT_DIR}/.env and fill required values." >&2
  exit 2
fi

export TELEGRAM_BOT_ENV_FILE="${ENV_FILE}"
REPOSITORY_ROOT=$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)
STATE_DIR="${SCRIPT_DIR}/state"
STATE_FILE="${STATE_DIR}/persona-release.json"
LOCK_DIR="${STATE_DIR}/persona-release.lock"

compose() {
  docker compose --env-file "${ENV_FILE}" --project-directory "${SCRIPT_DIR}" \
    -f "${COMPOSE_FILE}" "$@"
}

release_python() {
  PYTHONPATH="${REPOSITORY_ROOT}/src" python3 -m group_llm_agent.persona_release "$@"
}

require_release_arguments() {
  if [ "$#" -ne 3 ]; then
    usage
    exit 2
  fi
}

persona_preflight() {
  candidate_path=$1
  candidate_digest=$2
  report_path=$3
  mkdir -p "${STATE_DIR}"
  compose config >/dev/null
  running_services=$(compose ps --services --filter status=running)
  if [ "${running_services}" != "telegram-bot" ]; then
    echo "Persona preflight failed: the current Compose service is not running." >&2
    return 2
  fi
  release_python preflight \
    --repository-root "${REPOSITORY_ROOT}" \
    --env-file "${ENV_FILE}" \
    --candidate-path "${candidate_path}" \
    --candidate-digest "${candidate_digest}" \
    --report "${report_path}" \
    --state-file "${STATE_FILE}"
}

wait_for_persona_identity() {
  expected_version=$1
  expected_digest=$2
  attempt=0
  while [ "${attempt}" -lt 15 ]; do
    identity_logs=$(compose logs --no-color --tail=200 telegram-bot)
    case "${identity_logs}" in
      *"persona_bundle_loaded persona_id=lezhi persona_version=${expected_version} persona_digest=${expected_digest}"*)
        return 0
        ;;
    esac
    attempt=$((attempt + 1))
    sleep 2
  done
  return 2
}

persona_restore() {
  release_python restore-pins --env-file "${ENV_FILE}" --state-file "${STATE_FILE}"
  compose down
  compose up --detach --build
  if ! wait_for_persona_identity \
    lezhi-v1.0 25af6db13d2a9d4702a167ed99c685d3e934c6436eca491ce7de2ee58907a72a; then
    echo "Persona rollback failed: v1 startup identity was not observed." >&2
    return 2
  fi
  echo "Persona rollback completed: lezhi-v1.0 is running."
}

persona_release() {
  candidate_path=$1
  candidate_digest=$2
  report_path=$3
  mkdir -p "${STATE_DIR}"
  if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
    echo "Another persona release already owns the deployment lock." >&2
    return 2
  fi
  trap 'rmdir "${LOCK_DIR}" 2>/dev/null || true' EXIT HUP INT TERM
  persona_preflight "${candidate_path}" "${candidate_digest}" "${report_path}"
  release_python set-pins \
    --env-file "${ENV_FILE}" \
    --bundle-path "${candidate_path}" \
    --digest "${candidate_digest}"
  if ! compose down || ! compose up --detach --build; then
    echo "Persona activation failed; restoring the recorded v1 selectors." >&2
    persona_restore
    return 2
  fi
  if ! wait_for_persona_identity lezhi-v2.0 "${candidate_digest}"; then
    echo "Persona activation identity was not observed; restoring v1." >&2
    persona_restore
    return 2
  fi
  chat_id=$(release_python environment-chat-id --env-file "${ENV_FILE}")
  database_path=$(release_python environment-database-path --env-file "${ENV_FILE}")
  baseline=$(compose exec -T telegram-bot python -m group_llm_agent.persona_release \
    smoke-baseline --database "${database_path}" --chat-id "${chat_id}")
  release_python record-baseline --state-file "${STATE_FILE}" --inbound-id "${baseline}"
  echo "Persona release is running with lezhi-v2.0; send one direct Telegram message, then run persona-smoke."
}

persona_smoke() {
  chat_id=$(release_python environment-chat-id --env-file "${ENV_FILE}")
  database_path=$(release_python environment-database-path --env-file "${ENV_FILE}")
  set -- $(release_python state-smoke-arguments --state-file "${STATE_FILE}")
  baseline=$1
  candidate_digest=$2
  if ! compose exec -T telegram-bot python -m group_llm_agent.persona_release \
    smoke-verify --database "${database_path}" \
    --chat-id "${chat_id}" --baseline-id "${baseline}" \
    --persona-version lezhi-v2.0 --persona-digest "${candidate_digest}"; then
    echo "Persona Telegram smoke failed; restoring v1." >&2
    persona_restore
    return 2
  fi
}

case "$1" in
  build)
    [ "$#" -eq 1 ] || { usage; exit 2; }
    compose build
    ;;
  start)
    [ "$#" -eq 1 ] || { usage; exit 2; }
    compose up --detach --build
    ;;
  stop)
    [ "$#" -eq 1 ] || { usage; exit 2; }
    compose down
    ;;
  restart)
    [ "$#" -eq 1 ] || { usage; exit 2; }
    compose down
    compose up --detach --build
    ;;
  status)
    [ "$#" -eq 1 ] || { usage; exit 2; }
    compose ps
    ;;
  logs)
    [ "$#" -eq 1 ] || { usage; exit 2; }
    compose logs --follow --tail=200
    ;;
  persona-preflight)
    shift
    require_release_arguments "$@"
    persona_preflight "$@"
    ;;
  persona-release)
    shift
    require_release_arguments "$@"
    persona_release "$@"
    ;;
  persona-smoke)
    [ "$#" -eq 1 ] || { usage; exit 2; }
    persona_smoke
    ;;
  persona-rollback)
    [ "$#" -eq 1 ] || { usage; exit 2; }
    persona_restore
    ;;
  *)
    usage
    exit 2
    ;;
esac
