---
description: Merge open PRs into staging branch (excludes dependabot)
---

## Purpose

Merge all **open** PRs (excluding dependabot and draft PRs) into the staging branch, run lint checks and tests, then push.

**Important**: Only PRs that are:
- State "open" (not closed or merged)
- Not draft PRs (ready for review)
- Not from dependabot

## Process

### Step 1: List Open PRs

Get all open PRs excluding dependabot and drafts:

```bash
gh pr list --state open --json number,headRefName,author,isDraft | jq '[.[] | select(.author.is_bot == false and .isDraft == false)]'
```

Display the PRs to the user in a table:

| PR # | Branch | Author |
|------|--------|--------|

Ask the user which PRs to merge (default: all listed PRs).

### Step 2: Prepare Staging Branch

```bash
git fetch origin
git checkout staging
git pull origin staging
```

### Step 3: Fetch PR Branches

For each PR number, fetch using GitHub's PR refs:

```bash
git fetch origin refs/pull/<PR_NUMBER>/head:pr-<PR_NUMBER>
```

### Step 4: Merge Each PR

For each PR, merge into staging:

```bash
git merge pr-<PR_NUMBER> --no-edit -m "Merge PR #<PR_NUMBER> into staging"
```

If merge conflicts occur:
1. Stop and report the conflict to the user
2. List the conflicting files
3. Ask how to proceed (resolve manually, skip PR, or abort)

### Step 5: Run Lint Checks

Run the CI lint checks in order:

```bash
isort . --check-only
black . --check
flake8 .
```

If lint fails:
1. Run `black .` to auto-fix formatting
2. Run `isort .` to auto-fix import order
3. Re-run checks to verify fixes
4. If still failing, report specific errors

### Step 6: Run Tests

```bash
pytest tests/ -v --tb=short
```

All tests must pass before proceeding.

### Step 7: Commit Lint Fixes (if any)

If auto-formatting made changes:

```bash
git add -A
git commit -m "Fix lint errors after merge"
```

### Step 8: Verify All PRs Merged

Check that no commits remain unmerged:

```bash
for pr in <PR_NUMBERS>; do
  git log staging..pr-$pr --oneline
done
```

Empty output for each PR confirms successful merge.

### Step 9: Push to Remote

Ask user for confirmation, then:

```bash
git push origin staging
```

## Output

Report summary:
- PRs merged successfully
- PRs skipped (if any)
- Lint fixes applied (if any)
- Test results
- Push status

## Error Handling

- **Merge conflict**: Stop, report files, ask user
- **Lint failure**: Auto-fix with black/isort, report if still failing
- **Test failure**: Stop, report failing tests, do not push
- **Push rejected**: Report error, suggest `git pull --rebase`
