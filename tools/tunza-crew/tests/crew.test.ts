import { describe, expect, test } from 'claude-code/testing'

import { claimText, overlaps, parseClaim } from '../hooks/register.tsx'

describe('claims', () => {
  test('a claim file round-trips', async () => {
    const text = claimText(
      {
        machine: '5090',
        task: 'wire pipeline into store',
        paths: ['lib/store.tsx', 'lib/clinical/'],
        claimed: '2026-10-06T12:00:00.000Z',
      },
      'clinical-contract-wave1',
    )
    const claim = parseClaim('vault/claims/5090--wire.md', text)
    expect(claim?.machine).toBe('5090')
    expect(claim?.task).toBe('wire pipeline into store')
    expect(claim?.paths).toEqual(['lib/store.tsx', 'lib/clinical/'])
  })

  test('a file without machine or task is not a claim', async () => {
    expect(parseClaim('vault/claims/x.md', 'task: orphan\n')).toBe(null)
  })

  test('an absolute Windows edit path overlaps a claimed folder', async () => {
    expect(overlaps('C:\\Users\\hirsc\\Tunza\\lib\\clinical\\state.ts', 'lib/clinical/')).toBe(true)
    expect(overlaps('/Users/evan/code/Tunza/lib/store.tsx', 'lib/store.tsx')).toBe(true)
    expect(overlaps('/Users/evan/code/Tunza/lib/storefront.tsx', 'lib/store.tsx')).toBe(false)
    expect(overlaps('/Users/evan/code/Tunza/lib/copy.ts', 'lib/clinical')).toBe(false)
  })
})
