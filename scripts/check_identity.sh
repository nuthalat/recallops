#!/bin/sh
set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root_dir"

legacy_name="recallops"

if matches=$(git grep -n -i "$legacy_name" -- ':!scripts/check_identity.sh'); then
    printf '%s\n' "Obsolete project identity found in tracked files:" >&2
    printf '%s\n' "$matches" >&2
    exit 1
fi

if [ -d "src/$legacy_name" ]; then
    printf '%s\n' "Obsolete Python package directory still exists." >&2
    exit 1
fi

printf '%s\n' "IncidentEcho identity audit passed."
