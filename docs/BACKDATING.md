# How backdating Git commits works

This repo is a working GTM engine **and** a worked example of commit backdating.
Every commit in this history was created on 2026-09-25 but carries a date between
2026-09-01 and 2026-09-24. Nothing about GitHub or Git verifies commit dates.

## Two timestamps per commit

```
$ git cat-file -p HEAD
tree 4b825dc...
parent 9f1c2e...
author    Jane <jane@x.com> 1756740720 -0700   <- when the change was written
committer Jane <jane@x.com> 1756740720 -0700   <- when it was committed/applied
```

- **Author date**: shown by `git log` by default.
- **Committer date**: changes on rebase / cherry-pick / amend. GitHub's
  contribution graph and "committed X days ago" use this one.

Both are plain text the client writes. Git trusts whatever your machine says.

## Setting them

```bash
# both dates, one commit
GIT_AUTHOR_DATE="2026-09-03T14:12:00" GIT_COMMITTER_DATE="2026-09-03T14:12:00" \
  git commit -m "feat: add scoring"

# --date only sets AUTHOR date; committer date stays "now"
git commit --date="2026-09-03T14:12:00" -m "..."

# fix the last commit
GIT_COMMITTER_DATE="2026-09-03T14:12:00" git commit --amend --no-edit --date="2026-09-03T14:12:00"

# rewrite a whole range (committer = author date)
git rebase --committer-date-is-author-date <base>
```

`scripts/backdate.sh` wraps the first form. This repo's history was built with it.

## Inspect it

```bash
git log --format='%h  author=%ad  committer=%cd  %s' --date=iso
```

If author and committer differ wildly, something was rebased or amended.

## What it does NOT fake (how to catch backdating)

| Signal | Why it leaks |
|---|---|
| **Push time** | GitHub records when refs actually arrived. Visible in the repo's activity feed / Events API (`gh api repos/OWNER/REPO/events`) — here every push is 2026-09-25. |
| **Repo created_at** | `gh api repos/OWNER/REPO --jq .created_at` is after every "commit". |
| **Signed commits** | GPG/SSH signatures sign the dates too, but only prove *who*, not *when*. |
| **CI runs / PRs / issues** | Server-timestamped; a 3-week history with zero CI runs is a tell. |
| **Dependency versions** | Code using a library released after its commit date. |
| **Wall-clock gaps** | 20 commits all pushed in one burst. |

## Legit uses

Importing history from another VCS, re-creating lost history, preserving
original timestamps during migrations, teaching (this repo).

## Not-legit uses

Faking a contribution graph for a job application, backfilling "work" for a
deadline, or misrepresenting when IP was created. Contracts, school honor
codes, and IP disputes often hinge on dates - and the server-side signals above
contradict you.
