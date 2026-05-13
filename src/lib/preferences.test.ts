import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  defaultPreferences,
  loadPreferences,
  savePreferences,
  type AppPreferences,
} from './preferences'

function makeStorage() {
  const state = new Map<string, string>()

  return {
    getItem: vi.fn((key: string) => state.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {
      state.set(key, value)
    }),
  }
}

describe('preferences', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('loads persisted language, paths, and options', () => {
    const storage = makeStorage()
    const persisted: AppPreferences = {
      language: 'zh-TW',
      sourceDir: '/media/source',
      outputFile: '/media/out.mp4',
      musicDir: '/media/music',
      photoDuration: 9,
      originalVolume: 0.3,
      musicVolume: 0.7,
    }

    storage.setItem('kiwi-merge-preferences', JSON.stringify(persisted))

    expect(loadPreferences(storage)).toEqual(persisted)
  })

  it('falls back to defaults when persisted data is invalid', () => {
    const storage = makeStorage()
    storage.setItem('kiwi-merge-preferences', '{"language":"fr"}')

    expect(loadPreferences(storage)).toEqual(defaultPreferences)
  })

  it('saves complete preferences payload', () => {
    const storage = makeStorage()
    const next: AppPreferences = {
      language: 'zh-TW',
      sourceDir: 'C:/clips',
      outputFile: 'C:/merged.mp4',
      musicDir: 'C:/music',
      photoDuration: 6.5,
      originalVolume: 0.15,
      musicVolume: 0.8,
    }

    savePreferences(storage, next)

    expect(storage.setItem).toHaveBeenCalledWith(
      'kiwi-merge-preferences',
      JSON.stringify(next),
    )
  })
})
