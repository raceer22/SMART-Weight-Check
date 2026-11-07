---
id: "s04-add-a-gitignore-so-junk-files-are-not-committe-2026-11-07"
status: "done"
priority: "high"
assignee: null
epic: "0 · Setup"
dueDate: null
created: "2026-11-07T09:00:00.000Z"
modified: "2026-11-06T23:34:07.114Z"
completedAt: "2026-11-06T23:34:07.114Z"
labels: ["setup", "beginner", "git"]
order: "b04"
---
# S04 · Add a .gitignore so junk files are not committed

**Time:** \~10 min · **Do first:** S01

**Why:** `git status` currently shows `__pycache__/` and `*.egg-info/` folders. These should never be committed.

## Steps

1. Create a file called `.gitignore` in the repo root.
2. Add these lines:

   ```
   __pycache__/
   *.egg-info/
   .venv/
   my_*.csv
   .DS_Store
   ```
3. Run `git status` and check the folders are gone from the list.
4. Commit: `git add .gitignore && git commit -m "chore: add gitignore"`, then `git push`.

## Done when

- [ ] `git status` no longer lists `__pycache__` or `egg-info`.

- [ ] The commit is pushed.

## Help

- Only one person should do this card. Tell the team when it's pushed.