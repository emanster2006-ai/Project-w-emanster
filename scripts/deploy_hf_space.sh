#!/bin/sh
# Push the API (the committed HEAD, not local changes) to a Hugging Face Docker Space.
#
#   scripts/deploy_hf_space.sh <hf-user>/<space-name>
#
# Log in first with `hf auth login` (or any git credential for huggingface.co).
# The Space gets only what the API image needs, plus a README with the Space settings.
set -eu

SPACE="${1:?usage: $0 <hf-user>/<space-name>}"
ROOT=$(git rev-parse --show-toplevel)
REV=$(git -C "$ROOT" rev-parse --short HEAD)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

git -C "$ROOT" archive HEAD | tar -x -C "$TMP"
rm -rf "$TMP/frontend" "$TMP/docs" "$TMP/data" "$TMP/.github"

cat > "$TMP/README.md" <<EOF
---
title: SecureRAG API
sdk: docker
app_port: 7860
pinned: false
---

API for SecureRAG, deployed from commit $REV.
Source, docs and the frontend: https://github.com/emanster2006-ai/Project-w-emanster
EOF

cd "$TMP"
git init -q -b main
git add -A
git -c user.name="$(git -C "$ROOT" config user.name)" \
    -c user.email="$(git -C "$ROOT" config user.email)" \
    commit -q -m "Deploy $REV"
git push --force "https://huggingface.co/spaces/$SPACE" main
echo "Pushed $REV to https://huggingface.co/spaces/$SPACE"
