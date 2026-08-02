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
  release_python restore-pins --env-file "${ENV_FILE}" --state-file "${STATE_FILE}" || return 1
  compose down || return 1
  compose up --detach --build || return 1
  if ! wait_for_persona_identity \
    lezhi-v1.0 25af6db13d2a9d4702a167ed99c685d3e934c6436eca491ce7de2ee58907a72a; then
    echo "Persona rollback failed: v1 startup identity was not observed." >&2
    return 2
  fi
  echo "Persona rollback completed: lezhi-v1.0 is running."
}

record_release_failure() {
  stage=$1
  rollback_status=$2
  release_python record-failure --state-file "${STATE_FILE}" \
    --stage "${stage}" --rollback-status "${rollback_status}" || true
}

rollback_after_failure() {
  stage=$1
  echo "Persona release failed at ${stage}; restoring v1." >&2
  record_release_failure "${stage}" attempted
  if persona_restore; then
    record_release_failure "${stage}" succeeded
  else
    record_release_failure "${stage}" failed
    echo "Persona rollback failed after ${stage}." >&2
  fi
  return 2
}

activate_candidate() {
  candidate_digest=$1
  RELEASE_FAILURE_STAGE=compose_down
  compose down || return 1
  RELEASE_FAILURE_STAGE=compose_up
  compose up --detach --build || return 1
  RELEASE_FAILURE_STAGE=running_state
  running_services=$(compose ps --services --filter status=running) || return 1
  [ "${running_services}" = "telegram-bot" ] || return 1
  RELEASE_FAILURE_STAGE=identity
  wait_for_persona_identity lezhi-v2.0 "${candidate_digest}" || return 1
  RELEASE_FAILURE_STAGE=chat_id
  chat_id=$(release_python environment-chat-id --env-file "${ENV_FILE}") || return 1
  RELEASE_FAILURE_STAGE=database_path
  database_path=$(release_python environment-database-path --env-file "${ENV_FILE}") || return 1
  RELEASE_FAILURE_STAGE=smoke_baseline
  baseline=$(compose exec -T telegram-bot python -m group_llm_agent.persona_release \
    smoke-baseline --database "${database_path}" --chat-id "${chat_id}") || return 1
  RELEASE_FAILURE_STAGE=record_baseline
  release_python record-baseline --state-file "${STATE_FILE}" \
    --trigger-evaluation-id "${baseline}" || return 1
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
  RELEASE_FAILURE_STAGE=compose_down
  if ! activate_candidate "${candidate_digest}"; then
    rollback_after_failure "${RELEASE_FAILURE_STAGE}"
    return 2
  fi
  echo "Persona release is running with lezhi-v2.0; send one direct Telegram message, then run persona-smoke."
}

verify_persona_smoke() {
  RELEASE_FAILURE_STAGE=chat_id
  chat_id=$(release_python environment-chat-id --env-file "${ENV_FILE}") || return 1
  RELEASE_FAILURE_STAGE=database_path
  database_path=$(release_python environment-database-path --env-file "${ENV_FILE}") || return 1
  RELEASE_FAILURE_STAGE=smoke_state
  smoke_arguments=$(release_python state-smoke-arguments --state-file "${STATE_FILE}") || return 1
  set -- ${smoke_arguments}
  [ "$#" -eq 2 ] || return 1
  baseline=$1
  candidate_digest=$2
  RELEASE_FAILURE_STAGE=running_state
  running_services=$(compose ps --services --filter status=running) || return 1
  [ "${running_services}" = "telegram-bot" ] || return 1
  RELEASE_FAILURE_STAGE=smoke_verify
  compose exec -T telegram-bot python -m group_llm_agent.persona_release \
    smoke-verify --database "${database_path}" \
    --chat-id "${chat_id}" --baseline-id "${baseline}" \
    --persona-version lezhi-v2.0 --persona-digest "${candidate_digest}"
}

persona_smoke() {
  RELEASE_FAILURE_STAGE=smoke_state
  if ! verify_persona_smoke; then
    rollback_after_failure "${RELEASE_FAILURE_STAGE}"
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
