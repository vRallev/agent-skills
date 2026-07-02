#!/usr/bin/env bash
set -euo pipefail

repo="${1:-.}"
base="${2:-}"
repo="$(git -C "$repo" rev-parse --show-toplevel)"

if [[ -z "$base" ]]; then
  base="$(git -C "$repo" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null || true)"
  if [[ -z "$base" ]] && git -C "$repo" show-ref --verify --quiet refs/remotes/origin/main; then
    base="origin/main"
  fi
  if [[ -z "$base" ]] && git -C "$repo" show-ref --verify --quiet refs/remotes/origin/master; then
    base="origin/master"
  fi
fi

if [[ -z "$base" ]] || ! git -C "$repo" rev-parse --verify --quiet "$base^{commit}" >/dev/null; then
  printf 'error: could not resolve base ref %s\n' "${base:-<none>}" >&2
  exit 2
fi

worktree_path_for_branch() {
  local branch="$1"
  git -C "$repo" worktree list --porcelain | awk -v target="refs/heads/$branch" '
    $1 == "worktree" { path = substr($0, 10) }
    $1 == "branch" && $2 == target { print path; exit }
  '
}

printf 'base\t%s\t%s\n' "$base" "$(git -C "$repo" rev-parse "$base")"
printf 'classification\tbranch\tremote_state\tbehind\tahead\tworktree\tworktree_state\tevidence\n'

git -C "$repo" for-each-ref --format='%(refname:short)' refs/heads | while IFS= read -r branch; do
  case "$branch" in
    main|master) continue ;;
  esac

  upstream="$(git -C "$repo" for-each-ref --format='%(upstream:short)' "refs/heads/$branch")"
  if [[ -n "$upstream" ]]; then
    if git -C "$repo" show-ref --verify --quiet "refs/remotes/$upstream"; then
      remote_state="present:$upstream"
    else
      remote_state="gone:$upstream"
    fi
  elif git -C "$repo" show-ref --verify --quiet "refs/remotes/origin/$branch"; then
    remote_state="present-untracked:origin/$branch"
  else
    remote_state="absent"
  fi

  read -r behind ahead < <(git -C "$repo" rev-list --left-right --count "$base...refs/heads/$branch")
  classification=""
  evidence=""

  if git -C "$repo" merge-base --is-ancestor "refs/heads/$branch" "$base"; then
    classification="direct-ancestor"
    evidence="tip-is-ancestor"
  else
    merge_count="$(git -C "$repo" rev-list --count --merges "$base..refs/heads/$branch")"
    cherry="$(git -C "$repo" cherry "$base" "refs/heads/$branch")"
    unique_count="$(printf '%s\n' "$cherry" | awk '$1 == "+" { count++ } END { print count + 0 }')"
    equivalent_count="$(printf '%s\n' "$cherry" | awk '$1 == "-" { count++ } END { print count + 0 }')"

    if [[ "$merge_count" -gt 0 ]]; then
      classification="manual-review"
      evidence="merge-commits:$merge_count,unique-patches:$unique_count"
    elif [[ "$unique_count" -eq 0 && "$equivalent_count" -gt 0 ]]; then
      classification="patch-equivalent"
      evidence="equivalent-patches:$equivalent_count"
    else
      classification="retain"
      evidence="unique-patches:$unique_count"
    fi
  fi

  worktree="$(worktree_path_for_branch "$branch")"
  if [[ -z "$worktree" ]]; then
    worktree="-"
    worktree_state="-"
  elif [[ ! -d "$worktree" ]]; then
    worktree_state="unavailable"
  elif [[ -n "$(git -C "$worktree" status --porcelain)" ]]; then
    worktree_state="dirty"
  else
    worktree_state="clean"
  fi

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$classification" "$branch" "$remote_state" "$behind" "$ahead" \
    "$worktree" "$worktree_state" "$evidence"
done
