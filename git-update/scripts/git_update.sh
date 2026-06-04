#!/usr/bin/env bash
set -u
set -o pipefail

die() {
  printf 'git-update: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
usage: git_update.sh [repo]

Fetch/prune and update local main/master from origin without checking them out.

positional arguments:
  repo        Repository path to update. Defaults to the current directory.
EOF
}

git_in() {
  local cwd="$1"
  shift
  git -C "$cwd" "$@"
}

ref_exists() {
  local repo="$1"
  local ref="$2"
  git_in "$repo" show-ref --verify --quiet "$ref"
}

rev_parse() {
  local repo="$1"
  local ref="$2"
  git_in "$repo" rev-parse --verify "$ref"
}

create_local_branch() {
  local repo="$1"
  local branch="$2"
  local remote_ref="$3"

  git_in "$repo" branch --track "$branch" "$remote_ref" >/dev/null ||
    die "could not create $branch at $remote_ref"
  printf 'created %s at %s\n' "$branch" "$remote_ref"
}

cleanup_worktree() {
  local repo="$1"
  local worktree="$2"
  local temp_parent="$3"

  if [[ -n "$worktree" && -d "$worktree" ]]; then
    git_in "$repo" worktree remove --force "$worktree" >/dev/null 2>&1 || true
  fi
  if [[ -n "$temp_parent" && -d "$temp_parent" ]]; then
    rm -rf "$temp_parent"
  fi
}

rebase_branch_without_checkout() {
  local repo="$1"
  local branch="$2"
  local remote_ref="$3"
  local local_ref="refs/heads/$branch"
  local old_oid remote_oid temp_parent worktree rebase_output new_oid ahead

  old_oid="$(rev_parse "$repo" "$local_ref")" ||
    die "could not resolve $local_ref"
  remote_oid="$(rev_parse "$repo" "$remote_ref")" ||
    die "could not resolve $remote_ref"

  if [[ "$old_oid" == "$remote_oid" ]]; then
    printf '%s already matches %s\n' "$branch" "$remote_ref"
    return 0
  fi

  temp_parent="$(mktemp -d "${TMPDIR:-/tmp}/git-update-worktree.XXXXXX")" ||
    die "could not create temporary worktree directory"
  worktree="$temp_parent/$branch"

  if ! git_in "$repo" worktree add --detach "$worktree" "$old_oid" >/dev/null 2>&1; then
    cleanup_worktree "$repo" "$worktree" "$temp_parent"
    die "could not create temporary worktree for $branch"
  fi

  rebase_output="$(git_in "$worktree" rebase "$remote_ref" 2>&1)"
  local rebase_status=$?
  if [[ $rebase_status -ne 0 ]]; then
    git_in "$worktree" rebase --abort >/dev/null 2>&1 || true
    cleanup_worktree "$repo" "$worktree" "$temp_parent"
    die "could not rebase $branch onto $remote_ref; local branch was not moved: $rebase_output"
  fi

  new_oid="$(rev_parse "$worktree" HEAD)" ||
    die "could not resolve rebased HEAD for $branch"
  cleanup_worktree "$repo" "$worktree" "$temp_parent"

  git_in "$repo" update-ref "$local_ref" "$new_oid" "$old_oid" ||
    die "could not update $local_ref; it may have changed during git-update"

  if [[ "$new_oid" == "$remote_oid" ]]; then
    printf 'updated %s to match %s\n' "$branch" "$remote_ref"
  else
    ahead="$(git_in "$repo" rev-list --count "$remote_ref..$local_ref")" ||
      die "updated $branch but could not compute ahead count"
    printf 'rebased %s onto %s; branch is %s commit(s) ahead\n' "$branch" "$remote_ref" "$ahead"
  fi
}

update_branch() {
  local repo="$1"
  local branch="$2"
  local remote_ref="refs/remotes/origin/$branch"
  local local_ref="refs/heads/$branch"

  if ! ref_exists "$repo" "$remote_ref"; then
    return 1
  fi

  if ! ref_exists "$repo" "$local_ref"; then
    create_local_branch "$repo" "$branch" "origin/$branch"
  else
    rebase_branch_without_checkout "$repo" "$branch" "origin/$branch"
  fi
  return 0
}

main() {
  local repo_arg="."
  local repo updated_any=0

  case "${1:-}" in
    -h|--help)
      usage
      return 0
      ;;
    "")
      ;;
    *)
      repo_arg="$1"
      ;;
  esac

  if [[ $# -gt 1 ]]; then
    usage >&2
    return 2
  fi

  repo="$(git -C "$repo_arg" rev-parse --show-toplevel 2>/dev/null)" ||
    die "$repo_arg is not inside a Git repository"

  printf 'repository: %s\n' "$repo"
  git_in "$repo" fetch --prune ||
    die "git fetch --prune failed"

  if update_branch "$repo" master; then
    updated_any=1
  fi
  if update_branch "$repo" main; then
    updated_any=1
  fi

  if [[ $updated_any -eq 0 ]]; then
    printf 'no origin/master or origin/main branch found\n'
  fi
}

main "$@"
