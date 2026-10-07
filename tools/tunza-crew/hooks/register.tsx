import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Claim, Crew } from '../types'

type Options = { machine?: string; boardUrl?: string }

const crew = atom({ plugin: 'tunza-crew', key: 'crew' } as const, null)

const CLAIMS_DIR = 'vault/claims'

/** Joins a relative repo path onto the session's working directory. */
const join = (root: string, rel: string) =>
  `${root.replace(/[\\/]$/, '')}/${rel}`

const slug = (text: string) =>
  text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 48) || 'task'

const norm = (path: string) => path.replace(/\\/g, '/').replace(/^\.\//, '')

/** Claim files are one per claim, so five machines never conflict on one table. */
export function parseClaim(file: string, text: string): Claim | null {
  const field = (name: string) =>
    text.match(new RegExp(`^${name}:\\s*(.*)$`, 'm'))?.[1]?.trim() ?? ''
  const machine = field('machine')
  const task = field('task')
  if (!machine || !task) return null
  const paths = field('paths')
    .split(',')
    .map(p => norm(p.trim()))
    .filter(Boolean)
  return { file, machine, task, paths, claimed: field('claimed') }
}

export function claimText(c: Omit<Claim, 'file'>, branch: string): string {
  return [
    `machine: ${c.machine}`,
    `task: ${c.task}`,
    `paths: ${c.paths.join(', ')}`,
    `claimed: ${c.claimed}`,
    `branch: ${branch}`,
    '',
    'One claim per file. Remove this file with /release when the task is done.',
    '',
  ].join('\n')
}

/** True when an edited path falls under a claimed path (file or folder). */
export function overlaps(edited: string, claimed: string): boolean {
  const a = norm(edited).toLowerCase()
  const b = norm(claimed).toLowerCase().replace(/\/$/, '')
  return a === b || a.endsWith(`/${b}`) || a.includes(`/${b}/`) || a.startsWith(`${b}/`)
}

async function scan($: EngineInterface): Promise<Crew> {
  const root = await $.session.cwd()
  const isTunza =
    (await $.fs.exists(join(root, 'vault/INDEX.md'))) &&
    (await $.fs.exists(join(root, 'DESIGN.md')))
  if (!isTunza) return { isTunza: false, branch: '', hasWave1: false, claims: [] }

  const head = await $.fs.read(join(root, '.git/HEAD')).catch(() => '')
  const branch = head.startsWith('ref: refs/heads/')
    ? head.slice('ref: refs/heads/'.length).trim()
    : head.trim().slice(0, 7) || 'unknown'
  const hasWave1 = await $.fs.exists(join(root, 'lib/clinical/contract.ts'))

  const claims: Claim[] = []
  const dir = join(root, CLAIMS_DIR)
  if (await $.fs.exists(dir)) {
    for (const entry of await $.fs.list(dir)) {
      if (entry.kind !== 'file' || !entry.name.endsWith('.md')) continue
      const text = await $.fs.read(`${dir}/${entry.name}`).catch(() => '')
      const claim = parseClaim(`${CLAIMS_DIR}/${entry.name}`, text)
      if (claim) claims.push(claim)
    }
  }
  return { isTunza, branch, hasWave1, claims }
}

async function refresh($: EngineInterface): Promise<Crew> {
  const next = await scan($)
  await update($, crew, () => next)
  return next
}

async function vaultDigest($: EngineInterface, machine: string, c: Crew): Promise<string> {
  const root = await $.session.cwd()
  const index = await $.fs.read(join(root, 'vault/INDEX.md')).catch(() => '')
  const sessions = await $.fs.list(join(root, 'vault/sessions')).catch(() => [])
  const latest = sessions
    .filter(s => s.kind === 'file' && s.name.endsWith('.md'))
    .map(s => s.name)
    .sort()
    .pop()
  const note = latest
    ? await $.fs.read(join(root, `vault/sessions/${latest}`)).catch(() => '')
    : ''
  const claims = c.claims.length
    ? c.claims.map(k => `- ${k.machine}: ${k.task} (${k.paths.join(', ') || 'no paths'})`).join('\n')
    : '- none'
  return [
    '# Tunza crew context (tunza-crew mod)',
    `This machine is "${machine}". Branch: ${c.branch}.` +
      (c.hasWave1 ? '' : ' The wave-1 clinical contract (lib/clinical/) is NOT on this checkout.'),
    'Five machines work this repo at once. Before editing a path another machine has claimed, stop and tell the person.',
    'Commit and push small and often on a task branch; pull before starting. Never push to main.',
    '',
    '## Active claims',
    claims,
    '',
    '## vault/INDEX.md',
    index.trim(),
    latest ? `\n## Latest session note (vault/sessions/${latest})\n${note.trim()}` : '',
  ].join('\n')
}

export const register: Register = (on, options) => {
  const opts = options as Options
  const machine = (opts.machine ?? '').trim() || 'unnamed'
  const board = (opts.boardUrl ?? '').trim()
  const boardAsk = board
    ? ` Then mirror it on the live crew board (${board}) with ArtifactData, one batch: ` +
      `claims/<claim file name without .md> {machine, task, paths, branch, status: "active"|"done", claimedAt}, ` +
      `machines/<machine> {name, focus, branch, updatedAt} (update, keep other fields), ` +
      `and a new log/<id> {machine, text, at}. Use the server's time, read before writing.`
    : ''

  on('session.start', async ($, e, next) => {
    const result = await next(e)
    await $.command.register({
      name: 'claim',
      description: 'Claim a Tunza task for this machine: /claim <task> | path, path',
      argumentHint: '<task> | <path>, <path>',
    })
    await $.command.register({
      name: 'release',
      description: 'Release one of this machine\'s Tunza claims: /release <task or file>',
      argumentHint: '<task>',
    })
    await $.command.register({
      name: 'handoff',
      description: 'End a Tunza session: vault note, release claims, commit, push',
    })
    await $.command.register({
      name: 'checkin',
      description: 'Put this machine on the live Tunza crew board: /checkin <what you are working on>',
      argumentHint: '<focus>',
    })
    await $.command.register({
      name: 'crew',
      description: 'Show every machine\'s Tunza claims',
    })
    await refresh($)
    $.clock.every(60_000, () => {
      void refresh($)
    })
    return result
  })

  on('turn.complete', async ($, e, next) => {
    await refresh($)
    return next(e)
  })

  on('prompt.compose', async ($, e, next) => {
    const result = await next(e)
    const c = await read($, crew)
    if (!c?.isTunza) return result
    const text = await vaultDigest($, machine, c)
    return {
      sections: [...result.sections, { id: 'tunza-crew:vault', text, scope: 'session' as const }],
    }
  })

  // Warn, not block: someone else's claim on a file this machine is about to edit.
  on('tool.call', async ($, e, next) => {
    const tool = String(e.tool)
    if (tool === 'Edit' || tool === 'Write' || tool === 'NotebookEdit') {
      const path = (e as { file_path?: string; notebook_path?: string }).file_path ??
        (e as { notebook_path?: string }).notebook_path ?? ''
      const c = await read($, crew)
      const theirs = c?.claims.find(
        k => k.machine !== machine && k.paths.some(p => overlaps(path, p)),
      )
      if (theirs) $.ui.toast(`${theirs.machine} has claimed this for "${theirs.task}"`)
    }
    return next(e)
  })

  on('command.run', { command: 'claim' }, async ($, e) => {
    const c = await refresh($)
    if (!c.isTunza) return { text: 'Not in the Tunza repo.' }
    const [taskPart, pathPart = ''] = e.args.split('|')
    const task = (taskPart ?? '').trim()
    if (!task) return { text: 'Usage: /claim <task> | path, path' }
    const paths = pathPart.split(',').map(p => norm(p.trim())).filter(Boolean)

    const clash = c.claims.filter(
      k => k.machine !== machine && k.paths.some(p => paths.some(q => overlaps(q, p) || overlaps(p, q))),
    )
    const claimed = new Date(await $.clock.now()).toISOString()
    const file = `${CLAIMS_DIR}/${slug(machine)}--${slug(task)}.md`
    await $.fs.write(
      join(await $.session.cwd(), file),
      claimText({ machine, task, paths, claimed }, c.branch),
    )
    await refresh($)

    const warn = clash.length
      ? `\nOverlaps: ${clash.map(k => `${k.machine} (${k.task})`).join(', ')}. Talk before editing.`
      : ''
    return {
      text: `Claimed "${task}" as ${machine}: ${file}${warn}`,
      context: [
        `The person claimed "${task}" (${file}). Pull first, then commit that file alone ` +
        `("claim: ${machine} ${task}") and push it on the current branch so the other machines see it.` +
        boardAsk,
      ],
    }
  })

  on('command.run', { command: 'release' }, async ($, e) => {
    const c = await refresh($)
    const want = e.args.trim().toLowerCase()
    const mine = c.claims.filter(k => k.machine === machine)
    const hit = mine.find(k => k.task.toLowerCase() === want || k.file.toLowerCase().includes(want))
    if (!want || !hit) {
      return {
        text: mine.length
          ? `Your claims: ${mine.map(k => k.task).join('; ')}. Use /release <task>.`
          : 'This machine holds no claims.',
      }
    }
    return {
      text: `Releasing "${hit.task}".`,
      context: [
        `Delete ${hit.file}, commit ("release: ${machine} ${hit.task}") and push on the current branch.` +
        boardAsk,
      ],
    }
  })

  on('command.run', { command: 'checkin' }, async ($, e) => {
    const c = await refresh($)
    if (!c.isTunza) return { text: 'Not in the Tunza repo.' }
    if (!board) return { text: 'No board URL set. Set it in /config (tunza-crew).' }
    if (machine === 'unnamed') return { text: 'Name this machine first: /config → tunza-crew → Machine name.' }
    const focus = e.args.trim()
    return {
      text: `Checking in ${machine} on the crew board.`,
      context: [
        `Check this machine in on the Tunza crew board (${board}) with ArtifactData. ` +
          `Read machines/${slug(machine)} first. Set or update it with {name: "${machine}", branch: "${c.branch}", ` +
          (focus ? `focus: ${JSON.stringify(focus)}, ` : '') +
          'os (detect it), updatedAt (now, ISO)}; keep person and role if already set, and ask the person for them if missing. ' +
          `Add log/<new id> {machine: "${machine}", text: "checked in", at}. Then git pull so this checkout matches the board's repo state.`,
      ],
    }
  })

  on('command.run', { command: 'crew' }, async $ => {
    const c = await refresh($)
    if (!c.isTunza) return { text: 'Not in the Tunza repo.' }
    const lines = c.claims.length
      ? c.claims.map(k => `${k.machine.padEnd(10)} ${k.task}  [${k.paths.join(', ')}]`)
      : ['No claims. Pull to see the newest.']
    return { text: [`branch ${c.branch} · you are ${machine}`, ...lines].join('\n') }
  })

  on('command.run', { command: 'handoff' }, async $ => {
    const c = await refresh($)
    if (!c.isTunza) return { text: 'Not in the Tunza repo.' }
    const mine = c.claims.filter(k => k.machine === machine)
    await $.prompt.submit({
      text:
        `Tunza handoff for machine "${machine}". Follow vault/INDEX.md's protocol: ` +
        '(1) update the vault pages this session changed; ' +
        `(2) write vault/sessions/<today>-${slug(machine)}.md with what changed, what was verified (gate output), and what is next; ` +
        `(3) for finished tasks, delete their claim files (${mine.map(k => k.file).join(', ') || 'none held'}); ` +
        '(4) run the gates that apply (npx tsc --noEmit, npm test, npm run lint), report failures honestly; ' +
        '(5) commit and push on the current task branch, never main.' +
        boardAsk,
    })
    return { text: 'Handoff started.' }
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const c = await read($, crew)
    if (!c?.isTunza || e.props.hasSurvey) return next(e)
    const { Box, Text } = $.ui.resolve(e)
    const mine = c.claims.filter(k => k.machine === machine)
    const others = c.claims.filter(k => k.machine !== machine)
    return (
      <Box flexDirection="column">
        <Text dimColor>
          Tunza · {machine} · {c.branch}
          {c.hasWave1 ? '' : ' · no wave-1 here'} · mine: {mine.map(k => k.task).join(', ') || 'none'}
        </Text>
        {others.length > 0 && (
          <Text dimColor>
            others: {others.map(k => `${k.machine}→${k.task}`).join(' · ')}
          </Text>
        )}
      </Box>
    )
  })
}
