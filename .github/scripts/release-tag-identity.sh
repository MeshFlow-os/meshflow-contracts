#!/usr/bin/env bash
set -euo pipefail

test "$#" -eq 3

tag_ref="$1"
[[ "$tag_ref" == refs/tags/?* ]]
git check-ref-format "$tag_ref"
[[ "$2" =~ ^[0-9a-f]{40}$ ]]
[[ "$3" =~ ^[0-9a-f]{40}$ ]]

test "$(git cat-file -t "$tag_ref")" = tag
tag_object_sha="$(git rev-parse "$tag_ref")"
peeled_commit_sha="$(git rev-parse "${tag_ref}^{commit}")"
test "$tag_object_sha" = "$2"
test "$peeled_commit_sha" = "$3"
printf '%s %s\n' "$tag_object_sha" "$peeled_commit_sha"
