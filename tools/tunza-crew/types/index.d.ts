export type Claim = {
  file: string
  machine: string
  task: string
  paths: string[]
  claimed: string
}

export type Crew = {
  isTunza: boolean
  branch: string
  hasWave1: boolean
  claims: Claim[]
}

declare module 'claude-code' {
  interface PluginState {
    'tunza-crew': { crew: Crew | null }
  }
}
