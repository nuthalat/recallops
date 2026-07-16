#!/bin/sh
set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
artifact_dir=${INCIDENTECHO_ARTIFACT_DIR:-"$root_dir/.artifacts/verification"}
project_name=${INCIDENTECHO_VERIFY_PROJECT:-incidentecho-verify}
image_name=${INCIDENTECHO_VERIFY_IMAGE:-incidentecho:verify}
compose_file="$root_dir/compose.verify.yaml"

mkdir -p "$artifact_dir/dist"

cleanup() {
    docker compose -f "$compose_file" -p "$project_name" down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

printf '%s\n' "[1/7] Auditing project identity"
"$root_dir/scripts/check_identity.sh"

printf '%s\n' "[2/7] Building the production image"
docker build --tag "$image_name" "$root_dir"

printf '%s\n' "[3/7] Building and installing the wheel in a clean container"
docker run --rm \
    --user "$(id -u):$(id -g)" \
    --env HOME=/tmp \
    --env UV_CACHE_DIR=/workspace/.artifacts/verification/uv-cache \
    --volume "$root_dir:/workspace" \
    --workdir /workspace \
    ghcr.io/astral-sh/uv:0.8.17-python3.13-alpine \
    uv build --wheel --out-dir /workspace/.artifacts/verification/dist
docker run --rm \
    --volume "$artifact_dir/dist:/dist:ro" \
    python:3.13-alpine \
    sh -c 'set -- /dist/*.whl; pip install --no-deps "$1" >/dev/null; python -c '\''import importlib.util; import incidentecho; assert importlib.util.find_spec("recall" + "ops") is None'\'''

printf '%s\n' "[4/7] Starting a clean database and applying migrations"
INCIDENTECHO_VERIFY_IMAGE="$image_name" docker compose \
    -f "$compose_file" -p "$project_name" up --detach --wait --wait-timeout 120 api

printf '%s\n' "[5/7] Exercising matched and quiet analysis paths"
INCIDENTECHO_VERIFY_IMAGE="$image_name" docker compose \
    -f "$compose_file" -p "$project_name" run --rm --no-deps \
    -e INCIDENTECHO_VERIFY_PHASE=initial verifier >"$artifact_dir/pre-restart.json"

printf '%s\n' "[6/7] Restarting the API and verifying persistence"
INCIDENTECHO_VERIFY_IMAGE="$image_name" docker compose \
    -f "$compose_file" -p "$project_name" restart api
INCIDENTECHO_VERIFY_IMAGE="$image_name" docker compose \
    -f "$compose_file" -p "$project_name" up --detach --wait --wait-timeout 120 api
INCIDENTECHO_VERIFY_IMAGE="$image_name" docker compose \
    -f "$compose_file" -p "$project_name" run --rm --no-deps \
    -e INCIDENTECHO_VERIFY_PHASE=persistence verifier >"$artifact_dir/verification-receipt.json"

printf '%s\n' "[7/7] Verification complete"
printf 'Receipt: %s\n' "$artifact_dir/verification-receipt.json"
