# Claims

One file per claim, written by the tunza-crew mod's `/claim` and removed by
`/release` or `/handoff`. A file holds `machine:`, `task:`, `paths:`,
`claimed:` and `branch:` lines. One file per claim means two machines never
edit the same file to claim work, so claims never merge-conflict.

Before editing a path another machine has claimed, talk to them first. Live
view: the crew board (see `tools/tunza-crew/README.md`).
