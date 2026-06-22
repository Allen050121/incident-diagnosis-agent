# Codex And Claude Collaboration Policy

This project may be worked on by Codex and Claude against the same `.ai-team` workflow state.

## Shared Source Of Truth

- Task cards in `.ai-team/tasks/` are the human-readable source of work scope.
- `.ai-team/state/tasks.json` is the compact task index.
- `.ai-team/state/runs.json` is the execution and review evidence ledger.
- `.ai-team/state/collaboration.json` records active sessions and handoffs between clients.
- Durable product facts belong in `.ai-team/memory/`, not in client chat history.

## Startup Rules

Before editing, every client should:

1. Run `.ai-team/scripts/Get-AiTeamStatus.ps1`.
2. Check `.ai-team/state/collaboration.json` for active work on the same task.
3. Run `.ai-team/scripts/Get-AiTeamContext.ps1 -TaskId <task-id> -Mode compact` before implementation.
4. Start a collaboration session with `.ai-team/scripts/Update-AiTeamCollaboration.ps1 -Action start -Client <codex|claude> -TaskId <task-id> -Role <role>`.

## Conflict Rules

- Do not have Codex and Claude edit the same task card or the same implementation files at the same time.
- If another client has an active session on the same task, either continue as reviewer, ask the Human Lead, or wait for a handoff.
- Use separate branches or worktrees when two implementation tasks must move in parallel.
- Prefer one executor and one reviewer over two executors on the same task.

## Handoff Rules

When stopping mid-task, the active client must record:

- what changed,
- what was verified,
- what still needs a decision,
- what the next client should do first.

Use:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .ai-team/scripts/Update-AiTeamCollaboration.ps1 -Action handoff -Client codex -TaskId <task-id> -Summary "..." -NextAction "..."
```

When a task is fully released or no longer active, clear the active session with `-Action complete`.

