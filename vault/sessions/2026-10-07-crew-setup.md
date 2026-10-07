# 2026-10-07 — crew setup (machine: 5090)

Windows 11, RTX 5090. Set up so five computers can work Tunza at once.

## Changed

- `tools/tunza-crew/`: Claude Code mod. Vault digest at session start on every
  OS, a band showing this machine's and other machines' claims, `/claim`,
  `/release`, `/checkin`, `/crew`, `/handoff`. Claims are one file each in
  `vault/claims/`.
- `.claude-plugin/marketplace.json`: makes the repo a plugin marketplace, so a
  machine installs with `/plugin install tunza-crew --marketplace tunza-labs/Tunza`.
- Live crew board (claude.ai artifact with a shared database): repo state,
  machines, claims, activity. The repo stays the source of truth.
- `.gitattributes`: `eol=lf`. `tsconfig.json` and `eslint.config.mjs` skip `tools/`.

## Verified

- Mod: `claude plugin validate` passes, 3/3 mod tests, `tsc` clean on its own config.
- On this Windows checkout before `.gitattributes`: `tsc` clean, `npm test`
  144/145. The failure is `tests/eval-baseline.test.ts`: git's autocrlf
  rewrote `lib/assessment.ts` to CRLF, so its SHA-256 no longer matched the
  frozen `decider_sha256`. Not a code change. Existing Windows checkouts need
  a re-checkout after this merges.

## Next

- Each machine: install the mod, set its name, `/checkin`.
- Share the board with the crew as Contributors.
