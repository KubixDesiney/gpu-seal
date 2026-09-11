#!/usr/bin/env bash
# Build the GPU-SEAL probe container.
#
#   bash lab/docker/build.sh dev       # unpinned, works today, NOT publishable
#   bash lab/docker/build.sh release   # hash-pinned, publishable evidence
#
# Records the resulting image digest so it can be cited in result bundles
# (CHARTER.md §10: container_digest).

set -euo pipefail

PROFILE="${1:-dev}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

DOCKER_BIN="${DOCKER_BIN:-docker}"
if ! "$DOCKER_BIN" info --format='{{.ServerVersion}}' >/dev/null 2>&1; then
  if command -v docker.exe >/dev/null 2>&1 \
      && docker.exe info --format='{{.ServerVersion}}' >/dev/null 2>&1; then
    DOCKER_BIN=docker.exe
  else
    echo "ERROR: Docker daemon is unavailable through docker or docker.exe." >&2
    exit 1
  fi
fi

GIT_COMMIT="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
BUILD_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

case "$PROFILE" in
  dev)
    DOCKERFILE=infrastructure/containers/Dockerfile.dev
    TAG=gpu-seal:dev
    echo "Building UNPINNED dev image. Results will not be publishable."
    ;;
  release)
    DOCKERFILE=infrastructure/containers/Dockerfile
    TAG=gpu-seal:0.1.0
    if [ -n "$(git status --porcelain=v1 --untracked-files=all)" ]; then
      echo "ERROR: refusing a release image from a dirty working tree."
      echo "Commit or remove all changes before building publishable evidence."
      exit 1
    fi
    if grep -q "PLACEHOLDER" infrastructure/containers/requirements-lock.txt; then
      echo "ERROR: requirements-lock.txt still contains placeholder hashes."
      echo "Generate a real lock file first:"
      echo "    bash lab/docker/generate-lockfile.sh"
      exit 1
    fi
    ;;
  *)
    echo "Usage: $0 [dev|release]"; exit 1 ;;
esac

echo "Dockerfile : $DOCKERFILE"
echo "Tag        : $TAG"
echo "Commit     : $GIT_COMMIT"
echo

"$DOCKER_BIN" build \
  -f "$DOCKERFILE" \
  -t "$TAG" \
  --build-arg GIT_COMMIT="$GIT_COMMIT" \
  --build-arg BUILD_TIMESTAMP="$BUILD_TS" \
  .

echo
DIGEST="$("$DOCKER_BIN" image inspect --format='{{.Id}}' "$TAG")"
echo "image id: $DIGEST"

mkdir -p .provenance
{
  echo "tag=$TAG"
  echo "image_id=$DIGEST"
  echo "git_commit=$GIT_COMMIT"
  echo "build_timestamp=$BUILD_TS"
  echo "profile=$PROFILE"
} > ".provenance/container-${PROFILE}.txt"
echo "provenance written to .provenance/container-${PROFILE}.txt"
