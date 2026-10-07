# tunza-crew

A Claude Code mod for working on Tunza from several computers at once. It does
nothing outside this repo.

## Join a new computer

1. Clone the repo and install Git (Windows: `winget install Git.Git`).
2. In a Claude Code terminal session, install the mod:

   ```
   /plugin install tunza-crew --marketplace tunza-labs/Tunza
   ```

   Answer `y` to add the marketplace, then pick the user scope.
3. `/config` → tunza-crew → set **Machine name** (`5090`, `evan-mac`, `lenovo`, ...).
   **Live board URL** defaults to the crew board.
4. Ask the board's owner to share the board with you as a Contributor.
5. In the repo, run `/checkin <what you're working on>`. Your machine appears on the board.

## What it does

- **Context at start**: feeds `vault/INDEX.md`, the latest session note and every
  active claim into the system prompt. Works on Windows, macOS and Linux (the
  bash SessionStart hook needs bash).
- **Band above the prompt**: this machine, the branch, your claims, everyone else's.
- **`/claim <task> | path, path`**: writes `vault/claims/<machine>--<task>.md`
  (one file per claim, so machines never conflict) and has Claude commit, push,
  and mirror it to the board. Warns on overlap with another machine's paths.
- **`/release <task>`**, **`/crew`**, **`/checkin <focus>`**.
- **`/handoff`**: vault session note, release finished claims, gates, push to the
  task branch, board update.
- A toast when Claude is about to edit a path another machine claimed. It warns;
  it does not block.

The repo is the source of truth. The board is the live view of it.

## Developing it

```
claude plugin validate tools/tunza-crew
claude plugin test tools/tunza-crew
claude --plugin-dir tools/tunza-crew
```

The app's `tsc` and `eslint` skip `tools/`: the mod runs in Claude Code's plugin
runtime, not Next.js, and the engine writes its types into
`.claude-plugin/types/` on load (gitignored).
