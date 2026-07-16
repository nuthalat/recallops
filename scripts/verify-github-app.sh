#!/bin/sh
set -eu

: "${INCIDENTECHO_GITHUB_APP_ID:?set INCIDENTECHO_GITHUB_APP_ID}"
: "${INCIDENTECHO_GITHUB_INSTALLATION_ID:?set INCIDENTECHO_GITHUB_INSTALLATION_ID}"
: "${INCIDENTECHO_GITHUB_APP_PRIVATE_KEY_FILE:?set INCIDENTECHO_GITHUB_APP_PRIVATE_KEY_FILE}"

IMAGE="${INCIDENTECHO_VERIFY_IMAGE:-incidentecho:github-app-verify}"
KEY_FILE="$(cd "$(dirname "$INCIDENTECHO_GITHUB_APP_PRIVATE_KEY_FILE")" && pwd)/$(basename "$INCIDENTECHO_GITHUB_APP_PRIVATE_KEY_FILE")"

docker build --tag "$IMAGE" .
docker run --rm \
  --read-only \
  --network bridge \
  --mount "type=bind,source=$KEY_FILE,target=/run/secrets/github-app.pem,readonly" \
  "$IMAGE" python -m incidentecho.github.verify \
  --app-id "$INCIDENTECHO_GITHUB_APP_ID" \
  --private-key-file /run/secrets/github-app.pem \
  --installation-id "$INCIDENTECHO_GITHUB_INSTALLATION_ID" \
  --app-slug "${INCIDENTECHO_GITHUB_APP_SLUG:-incidentecho-dev}" \
  --owner "${INCIDENTECHO_GITHUB_OWNER:-IncidentEcho}" \
  --repository "${INCIDENTECHO_GITHUB_REPOSITORY:-incidentecho}"
