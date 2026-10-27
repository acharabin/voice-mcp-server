#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${PROJECT_DIR}/logs"
LOG_FILE="${LOG_DIR}/log.txt"
APP_SERVICE="${APP_SERVICE:-voice-ai.service}"
APP_HEALTH_URL="${APP_HEALTH_URL:-http://127.0.0.1:10001/auth/config}"
KEYCLOAK_HEALTH_URL="${KEYCLOAK_HEALTH_URL:-http://127.0.0.1:8081/auth/realms/voice-ai/.well-known/openid-configuration}"
COMPOSE_ENV="${COMPOSE_ENV:-${PROJECT_DIR}/.env.public}"
COMPOSE_FILE="${COMPOSE_FILE:-${PROJECT_DIR}/docker-compose.public.yml}"

mkdir -p "$LOG_DIR"
if [[ -f "$LOG_FILE" ]] && (( $(stat -c '%s' "$LOG_FILE") > 10485760 )); then
    tail -n 5000 "$LOG_FILE" >"${LOG_FILE}.tmp"
    mv "${LOG_FILE}.tmp" "$LOG_FILE"
fi
exec >>"$LOG_FILE" 2>&1

log() {
    printf '[%s] %s\n' "$(date --iso-8601=seconds)" "$*"
}

trap 'status=$?; log "ERROR at line ${LINENO} (exit ${status})"' ERR

exec 9>"${LOG_DIR}/restart-deployment.lock"
if ! flock -n 9; then
    log "Another deployment check is already running; skipping."
    exit 0
fi

wait_for_url() {
    local url="$1"
    local attempts="${2:-10}"
    local delay="${3:-5}"
    local attempt

    for ((attempt = 1; attempt <= attempts; attempt++)); do
        if curl --fail --silent --show-error --max-time 5 "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep "$delay"
    done
    return 1
}

dump_service_logs() {
    local service="$1"
    log "Recent journal output for ${service}:"
    journalctl -u "$service" -n 100 --no-pager || true
}

log "Deployment health check started."

if [[ ! -f "$COMPOSE_ENV" || ! -f "$COMPOSE_FILE" ]]; then
    log "Missing ${COMPOSE_ENV} or ${COMPOSE_FILE}; cannot ensure the public Keycloak stack is running."
    exit 1
fi

if ! systemctl is-active --quiet docker; then
    log "Docker is not active; starting it."
    systemctl start docker
fi

docker compose --env-file "$COMPOSE_ENV" -f "$COMPOSE_FILE" up -d

if ! systemctl is-active --quiet caddy; then
    log "Caddy is not active; starting it."
    systemctl start caddy
fi

if ! wait_for_url "$KEYCLOAK_HEALTH_URL" 12 5; then
    log "Keycloak discovery endpoint did not become healthy; restarting the Keycloak container."
    docker compose --env-file "$COMPOSE_ENV" -f "$COMPOSE_FILE" restart keycloak
    if ! wait_for_url "$KEYCLOAK_HEALTH_URL" 12 5; then
        log "Keycloak is still unavailable. Recent container logs:"
        docker compose --env-file "$COMPOSE_ENV" -f "$COMPOSE_FILE" logs --tail 100 keycloak keycloak-db || true
        exit 1
    fi
fi

if ! wait_for_url "$APP_HEALTH_URL" 10 5; then
    log "Voice app health endpoint did not respond; restarting ${APP_SERVICE}."
    systemctl restart "$APP_SERVICE"
    if ! wait_for_url "$APP_HEALTH_URL" 12 5; then
        log "Voice app is still unavailable after restart."
        dump_service_logs "$APP_SERVICE"
        exit 1
    fi
    dump_service_logs "$APP_SERVICE"
fi

log "Deployment is healthy: app, Keycloak, and Caddy are available."
