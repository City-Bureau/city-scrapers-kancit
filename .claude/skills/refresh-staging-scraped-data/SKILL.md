---
description: Refresh staging scraped data - merge PRs, clean Azure, reset DB, import
---

## Quick Start

To run this skill, use Claude Code and type:

```
/refresh-staging-scraped-data
```

Claude will guide you through each step interactively, asking for confirmation before destructive actions (like cleaning Azure or pushing to staging).

## Purpose

Complete workflow to refresh staging scraped data:

1. Clean up raw meeting data in Azure (delete all data in container)
2. Merge latest code from PRs to staging branch (lint, test, push)
3. Remove meetings data from staging Heroku database
4. Run import data command after scraping cron completes

## Environment Variables

The following env vars must be set in `.env` (example):

```bash
# Azure Storage
AZURE_ACCOUNT_NAME=cityscrapers
AZURE_ACCOUNT_KEY=<your-key>
AZURE_CONTAINER=meetings-feed-colgo-stg

# Program settings
PROGRAM_SLUG=columbia-gorge
PROGRAM_NAME=columbia
```

**IMPORTANT**: Heroku app is hardcoded to `documenters-stg` to prevent accidental production data loss.

## Process

### Step 1: Clean Azure Container

Ask user to confirm before cleaning the Azure container.

Load environment variables and delete all blobs in the staging container:

```bash
# Load env vars (export for use in commands)
export $(grep -v '^#' .env | xargs)

# List current blobs (to show what will be deleted)
az storage blob list --account-name "$AZURE_ACCOUNT_NAME" --account-key "$AZURE_ACCOUNT_KEY" --container-name "$AZURE_CONTAINER" --output table

# Delete all blobs in the container
az storage blob delete-batch --account-name "$AZURE_ACCOUNT_NAME" --account-key "$AZURE_ACCOUNT_KEY" --source "$AZURE_CONTAINER"
```

Verify the container is empty:

```bash
az storage blob list --account-name "$AZURE_ACCOUNT_NAME" --account-key "$AZURE_ACCOUNT_KEY" --container-name "$AZURE_CONTAINER" --output table
```

Expected: No blobs listed (empty container).

### Step 2: List Open PRs

Get all open PRs excluding dependabot and drafts:

```bash
gh pr list --state open --json number,headRefName,author,isDraft | jq '[.[] | select(.author.is_bot == false and .isDraft == false)]'
```

Display the PRs to the user in a table:

| PR # | Branch | Author |
|------|--------|--------|

Ask the user which PRs to merge (default: all listed PRs).

### Step 3: Prepare Staging Branch

```bash
git fetch origin
git checkout staging
git pull origin staging
```

### Step 4: Fetch PR Branches

For each PR number, fetch using GitHub's PR refs:

```bash
git fetch origin refs/pull/<PR_NUMBER>/head:pr-<PR_NUMBER>
```

### Step 5: Merge Each PR

For each PR, merge into staging:

```bash
git merge pr-<PR_NUMBER> --no-edit -m "Merge PR #<PR_NUMBER> into staging"
```

If merge conflicts occur:
1. Stop and report the conflict to the user
2. List the conflicting files
3. Ask how to proceed (resolve manually, skip PR, or abort)

### Step 6: Run Lint Checks

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

### Step 7: Run Tests

```bash
pytest tests/ -v --tb=short
```

All tests must pass before proceeding.

### Step 8: Commit Lint Fixes (if any)

If auto-formatting made changes:

```bash
git add -A
git commit -m "Fix lint errors after merge"
```

### Step 9: Verify All PRs Merged

Check that no commits remain unmerged:

```bash
for pr in <PR_NUMBERS>; do
  git log staging..pr-$pr --oneline
done
```

Empty output for each PR confirms successful merge.

### Step 10: Push to Remote

Ask user for confirmation, then:

```bash
git push origin staging
```

After push, the GitHub Actions scraping cron will run automatically.

**Important**: Tell user to monitor the GitHub Actions at:

```bash
echo "$(gh repo view --json url -q .url)/actions/workflows/staging.yml"
```

There will be 2 jobs triggered:
1. **CI** - runs lint/tests, completes quickly
2. **crawl** - runs the scrapers, takes about **30 minutes** to complete

Wait for the **crawl** job to finish before proceeding to Step 11.

### Step 11: Delete Meetings Without Assignments

**Wait for scraping to complete first!**

Ask user to confirm the scraping cron has completed successfully.

Then run the delete script via Heroku:

```bash
export $(grep -v '^#' .env | xargs)

heroku run python manage.py shell -a documenters-stg <<EOF
from documenters.meetings.models import Meeting

program_meetings = Meeting.objects.filter(programs__slug='$PROGRAM_SLUG')
total = program_meetings.count()
with_assignments = program_meetings.filter(assignments__isnull=False).distinct()
without_assignments = program_meetings.filter(assignments__isnull=True).distinct()

print(f'Total $PROGRAM_SLUG meetings: {total}')
print(f'With assignments: {len(with_assignments)}')
print(f'Without assignments: {len(without_assignments)}')

without_assignments.delete()
print('Deleted meetings without assignments')
EOF
```

### Step 12: Run Import Data

After deleting old meetings, run the import:

```bash
export $(grep -v '^#' .env | xargs)

heroku run python manage.py shell -a documenters-stg <<EOF
from documenters.accounts.models import Program
from documenters.meetings.tasks import handle_meetings_feed_endpoint

program = Program.objects.filter(name__icontains='$PROGRAM_NAME').first()
print(f'Queuing import from: {program.meetings_feed_endpoint}')
handle_meetings_feed_endpoint.send(program.meetings_feed_endpoint)
EOF
```

### Step 13: Monitor Import Progress

Monitor the import progress in Heroku logs:

**https://dashboard.heroku.com/apps/documenters-stg/logs**

Or via CLI:

```bash
heroku logs --tail -a documenters-stg
```

Look for log entries showing meetings being imported.

**Troubleshooting**: If no import logs appear, add this environment variable and rerun the import (Step 12):

```bash
heroku config:set SKIP_AZURE_BLOB_DATA_CHECK=true -a documenters-stg
```

Then rerun Step 12 to trigger the import again.

### Step 14: Verify Import Complete

After import finishes, verify the meeting count:

```bash
export $(grep -v '^#' .env | xargs)

heroku run python manage.py shell -a documenters-stg <<EOF
from documenters.meetings.models import Meeting

program_meetings = Meeting.objects.filter(programs__slug='$PROGRAM_SLUG')
total = program_meetings.count()
print(f'Total $PROGRAM_SLUG meetings: {total}')
EOF
```

### Step 15: Cleanup (if needed)

If you added `SKIP_AZURE_BLOB_DATA_CHECK` in Step 13, remove it now:

```bash
heroku config:unset SKIP_AZURE_BLOB_DATA_CHECK -a documenters-stg
```

## Output

Report summary:
- Azure container cleaned (via Azure CLI)
- PRs merged successfully
- PRs skipped (if any)
- Lint fixes applied (if any)
- Test results
- Push status
- Scraping workflow status
- Meetings deleted count
- Import queued status

## Error Handling

- **Azure CLI fails**: Check .env file exists and has correct credentials
- **Merge conflict**: Stop, report files, ask user
- **Lint failure**: Auto-fix with black/isort, report if still failing
- **Test failure**: Stop, report failing tests, do not push
- **Push rejected**: Report error, suggest `git pull --rebase`
- **Heroku command fails**: Report error, check Heroku status
- **Scraping fails**: Check GitHub Actions logs, report to user

## Notes

- Steps 11-12 require the **crawl** job to complete first (~30 minutes)
- Monitor the **crawl** workflow at the repo's GitHub Actions page
- Only meetings WITHOUT assignments are deleted (preserves historical data)
- To use for a different program, update `.env` with appropriate values:
  - `AZURE_CONTAINER` - the Azure blob container for the program
  - `PROGRAM_SLUG` - the program slug in the database (e.g., `columbia-gorge`)
  - `PROGRAM_NAME` - partial name match for the program (e.g., `columbia`)
- Heroku app is **always** `documenters-stg` (hardcoded to prevent production accidents)
