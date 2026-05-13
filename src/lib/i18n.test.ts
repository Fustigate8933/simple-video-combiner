import { describe, expect, it } from 'vitest'

import { messages, translate } from './i18n'

describe('i18n', () => {
  it('returns english copy', () => {
    expect(translate('en', 'appTitle')).toBe('Video merge control panel')
  })

  it('returns traditional chinese copy', () => {
    expect(translate('zh-TW', 'appTitle')).toBe('影片合併控制面板')
  })

  it('keeps language dictionaries in sync', () => {
    const englishKeys = Object.keys(messages.en).sort()
    const chineseKeys = Object.keys(messages['zh-TW']).sort()

    expect(chineseKeys).toEqual(englishKeys)
  })
})
