export type Language = 'en' | 'zh-TW'

export interface AppPreferences {
  language: Language
  sourceDir: string
  outputFile: string
  musicDir: string
  photoDuration: number
  originalVolume: number
  musicVolume: number
}

export interface PreferenceStorage {
  getItem: (key: string) => string | null
  setItem: (key: string, value: string) => void
}

export const PREFERENCES_KEY = 'kiwi-merge-preferences'

export const defaultPreferences: AppPreferences = {
  language: 'en',
  sourceDir: '',
  outputFile: '',
  musicDir: '',
  photoDuration: 7,
  originalVolume: 0.2,
  musicVolume: 0.85,
}

function isLanguage(value: unknown): value is Language {
  return value === 'en' || value === 'zh-TW'
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function isPreferences(value: unknown): value is AppPreferences {
  if (!value || typeof value !== 'object') {
    return false
  }

  const candidate = value as Record<string, unknown>
  return (
    isLanguage(candidate.language) &&
    typeof candidate.sourceDir === 'string' &&
    typeof candidate.outputFile === 'string' &&
    typeof candidate.musicDir === 'string' &&
    isFiniteNumber(candidate.photoDuration) &&
    isFiniteNumber(candidate.originalVolume) &&
    isFiniteNumber(candidate.musicVolume)
  )
}

export function loadPreferences(
  storage: PreferenceStorage | null = globalThis.localStorage ?? null,
): AppPreferences {
  if (!storage) {
    return defaultPreferences
  }

  try {
    const raw = storage.getItem(PREFERENCES_KEY)
    if (!raw) {
      return defaultPreferences
    }

    const parsed = JSON.parse(raw) as unknown
    return isPreferences(parsed) ? parsed : defaultPreferences
  } catch {
    return defaultPreferences
  }
}

export function savePreferences(
  storage: PreferenceStorage | null,
  preferences: AppPreferences,
): void {
  if (!storage) {
    return
  }

  storage.setItem(PREFERENCES_KEY, JSON.stringify(preferences))
}
