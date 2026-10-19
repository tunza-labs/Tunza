# v2 data notes (2026-10-19)

Engineering shakedown data only. Synthetic. Not clinical. Nothing here is a clinical sign-off.

## `triage-sealed.jsonl` is a public held-out set, not a sealed set
- It is committed to a public GitHub repo, so anyone can read it. It is no longer sealed.
- Use it as a public held-out comparison. Never train on it. Training and public-set rows share no story text, but 160 of its 450 rows share their structured answers with a training row, and a few dev symptom phrases appear inside its stories.
- Template families in this file are disjoint from the v2 training families (see `manifest.json`).
- A private test set made with the same generator and a different seed lives outside the repo. It uses the same template families as this file, so it protects against training on the exact public rows but is not an unseen-family set. A clinician-reviewed sealed gold set is still an unmet opening criterion.

## Reward version
- Results written from 2026-10-19 carry `reward_version: 2`. Version 2 closes three loopholes found in the audit: a danger fact must be a whole word or phrase of 3+ characters from the story, empty danger facts on a danger case cost 0.3 (was 0.1), and a follow-up question must be a real question (3+ words, one question mark at the end, no disposition name inside).
- Results without `reward_version` were scored with version 1. Do not compare mean rewards across versions. `danger_missed` depends on the disposition alone and is comparable.

## `data/triage-dev.jsonl` review notes
- Rows 5, 8, 10, 68, 71 are labeled `go_now` from danger words in the story while the structured fields look calm. This is intentional: it tests reading danger that appears only in free text.
- Row 44 (`kupumua kwake ni kugumu`, sleepy, breathing fine, label `get_care_today`) is ambiguous: the story says breathing is hard, and sleepy plus difficult breathing would be `go_now`. Keep it, but treat a miss there as inconclusive until a person reviews it.
- 16 `go_now` rows depend on a single keyword rule in `decide()`. That is a property of the demonstration rules, not of the rows.
