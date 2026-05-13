<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'

import LogPanel from './components/LogPanel.vue'
import OptionPanel from './components/OptionPanel.vue'
import type { MergeFormOptions } from './components/OptionPanel.vue'
import PathField from './components/PathField.vue'
import ProgressPanel from './components/ProgressPanel.vue'
import StatsPanel from './components/StatsPanel.vue'
import {
  ApiError,
  cancelJob,
  dryRun,
  getJob,
  scan,
  startJob,
  subscribeJob,
  type JobStatusResponse,
  type JobSubscription,
  type MergeOptions,
  type ScanResponse,
} from './lib/api'
import { translate, type MessageKey } from './lib/i18n'
import { loadPreferences, savePreferences, type Language } from './lib/preferences'

const savedPreferences = loadPreferences()
const localStorageRef = globalThis.localStorage ?? null

const language = ref<Language>(savedPreferences.language)
const form = reactive({
  sourceDir: savedPreferences.sourceDir,
  outputFile: savedPreferences.outputFile,
  musicDir: savedPreferences.musicDir,
  photoDuration: savedPreferences.photoDuration,
  originalVolume: savedPreferences.originalVolume,
  musicVolume: savedPreferences.musicVolume,
})

const stats = ref<ScanResponse | null>(null)
const logs = ref<string[]>([])
const errorMessage = ref<string | null>(null)
const activeAction = ref<'scan' | 'dry-run' | 'start' | 'cancel' | null>(null)
const jobId = ref<string | null>(null)
const jobStatus = ref('idle')
const subscription = ref<JobSubscription | null>(null)
const uiMessageKey = ref<MessageKey>('defaultMessage')
const lastScanMode = ref<'none' | 'scan' | 'dry-run'>('none')
const lastScanSummary = ref<ScanResponse | null>(null)

const t = (key: MessageKey) => translate(language.value, key)

const options = computed<MergeFormOptions>({
  get: () => ({
    photoDuration: form.photoDuration,
    originalVolume: form.originalVolume,
    musicVolume: form.musicVolume,
  }),
  set: (value) => {
    form.photoDuration = value.photoDuration
    form.originalVolume = value.originalVolume
    form.musicVolume = value.musicVolume
  },
})

const hasPathInputs = computed(() => Boolean(form.sourceDir && form.musicDir))
const hasAllInputs = computed(() => Boolean(form.sourceDir && form.outputFile && form.musicDir))
const isRunning = computed(() => jobStatus.value === 'pending' || jobStatus.value === 'running')
const isBusy = computed(() => activeAction.value !== null || isRunning.value)
const uiMessage = computed(() => t(uiMessageKey.value))
const lastScanLabel = computed(() => {
  if (!lastScanSummary.value || lastScanMode.value === 'none') {
    return t('runScanPrompt')
  }

  const { mp4_count, image_count, music_count } = lastScanSummary.value
  if (language.value === 'zh-TW') {
    if (lastScanMode.value === 'dry-run') {
      return `模擬執行已檢查 ${mp4_count} 部影片、${image_count} 張圖片、${music_count} 首音軌。`
    }

    return `找到 ${mp4_count} 部影片、${image_count} 張圖片、${music_count} 首音軌。`
  }

  if (lastScanMode.value === 'dry-run') {
    return `Dry run checked ${mp4_count} videos, ${image_count} images, ${music_count} tracks.`
  }

  return `Found ${mp4_count} videos, ${image_count} images, ${music_count} tracks.`
})
const statusLabels = computed(() => ({
  idle: t('statusIdle'),
  pending: t('statusPending'),
  running: t('statusRunning'),
  succeeded: t('statusSucceeded'),
  failed: t('statusFailed'),
  cancelled: t('statusCancelled'),
}))

function toMergeOptions(): MergeOptions {
  return {
    source_dir: form.sourceDir.trim(),
    output_file: form.outputFile.trim(),
    music_dir: form.musicDir.trim(),
    photo_duration: form.photoDuration,
    original_volume: form.originalVolume,
    music_volume: form.musicVolume,
  }
}

function pushLogs(lines: string[]) {
  if (!lines.length) {
    return
  }

  logs.value = [...logs.value, ...lines]
}

function appendLog(line: string) {
  pushLogs([line])
}

function setJobState(status: JobStatusResponse) {
  jobId.value = status.job_id
  jobStatus.value = status.status
  errorMessage.value = status.error
  logs.value = [...status.logs]
}

function resetSubscription() {
  subscription.value?.close()
  subscription.value = null
}

function startSubscription(currentJobId: string) {
  resetSubscription()

  const next = subscribeJob(
    currentJobId,
    (status) => {
      jobStatus.value = status
      if (status === 'succeeded') {
        uiMessageKey.value = 'mergeCompletedMessage'
      } else if (status === 'failed') {
        uiMessageKey.value = 'mergeFailedMessage'
      } else if (status === 'cancelled') {
        uiMessageKey.value = 'mergeCancelledMessage'
      }
    },
    (line) => {
      appendLog(line)
    },
  )

  next.done
    .then(async () => {
      const latest = await getLatestJobState(currentJobId)
      setJobState(latest)
    })
    .catch((error: unknown) => {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return
      }

      const message = error instanceof ApiError ? error.detail : t('liveUpdatesStopped')
      errorMessage.value = message
      appendLog(message)
    })
    .finally(() => {
      if (subscription.value === next) {
        subscription.value = null
      }
    })

  subscription.value = next
}

async function getLatestJobState(currentJobId: string) {
  return getJob(currentJobId)
}

function handleError(error: unknown, fallback: string) {
  const message = error instanceof ApiError ? error.detail : fallback
  errorMessage.value = message
  appendLog(message)
}

async function runScan() {
  if (!hasPathInputs.value) {
    errorMessage.value = t('scanValidationError')
    return
  }

  errorMessage.value = null
  activeAction.value = 'scan'

  try {
    const response = await scan(form.sourceDir.trim(), form.musicDir.trim())
    stats.value = response
    lastScanSummary.value = response
    lastScanMode.value = 'scan'
    uiMessageKey.value = 'scanCompleteMessage'
    appendLog(
      `Scan complete: ${response.mp4_count} videos, ${response.image_count} images, ${response.music_count} tracks.`,
    )
  } catch (error) {
    handleError(error, t('scanFailedFallback'))
  } finally {
    activeAction.value = null
  }
}

async function runDryRun() {
  if (!hasAllInputs.value) {
    errorMessage.value = t('dryRunValidationError')
    return
  }

  errorMessage.value = null
  activeAction.value = 'dry-run'

  try {
    const response = await dryRun(toMergeOptions())
    stats.value = response.summary
    lastScanSummary.value = response.summary
    lastScanMode.value = 'dry-run'
    uiMessageKey.value = 'dryRunCompleteMessage'
    pushLogs([
      t('dryRunHeader'),
      ...response.messages,
      `${t('commandLabel')}: ${response.command_text}`,
    ])
  } catch (error) {
    handleError(error, t('dryRunFailedFallback'))
  } finally {
    activeAction.value = null
  }
}

async function runStartJob() {
  if (!hasAllInputs.value) {
    errorMessage.value = t('startValidationError')
    return
  }

  errorMessage.value = null
  activeAction.value = 'start'
  logs.value = []

  try {
    const response = await startJob(toMergeOptions())
    setJobState(response)
    uiMessageKey.value = 'mergeStartedMessage'
    startSubscription(response.job_id)
  } catch (error) {
    handleError(error, t('startFailedFallback'))
  } finally {
    activeAction.value = null
  }
}

async function runCancel() {
  if (!jobId.value) {
    return
  }

  errorMessage.value = null
  activeAction.value = 'cancel'

  try {
    const response = await cancelJob(jobId.value)
    setJobState(response)
    uiMessageKey.value = 'mergeCancelledMessage'
  } catch (error) {
    handleError(error, t('cancelFailedFallback'))
  } finally {
    activeAction.value = null
  }
}

async function pickDirectory(field: 'sourceDir' | 'musicDir') {
  const selected = await window.kiwi?.pickDirectory?.()
  if (!selected) {
    return
  }

  form[field] = selected
  if (hasPathInputs.value) {
    await runScan()
  }
}

async function pickOutput() {
  const selected = await window.kiwi?.pickOutputFile?.()
  if (!selected) {
    return
  }

  form.outputFile = selected
}

watch(
  () => ({
    language: language.value,
    sourceDir: form.sourceDir,
    outputFile: form.outputFile,
    musicDir: form.musicDir,
    photoDuration: form.photoDuration,
    originalVolume: form.originalVolume,
    musicVolume: form.musicVolume,
  }),
  (next) => {
    savePreferences(localStorageRef, next)
  },
  { deep: true },
)

onBeforeUnmount(() => {
  resetSubscription()
})
</script>

<template>
  <main class="min-h-screen bg-white px-4 py-6 text-[#23301e] sm:px-6 lg:px-8">
    <div class="mx-auto max-w-7xl">
      <section class="rounded-md border border-[#d9e2cf] bg-white p-5 sm:p-6">
        <div class="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h1 class="mt-2 text-2xl font-semibold sm:text-3xl">{{ t('appTitle') }}</h1>
            <p class="mt-2 max-w-2xl text-sm text-[#66735e]">{{ uiMessage }}</p>
          </div>
          <div class="flex items-center gap-3 self-start">
            <span class="text-xs font-medium uppercase tracking-wide text-[#66735e]">
              {{ t('languageLabel') }}
            </span>
            <div class="inline-flex rounded-md border border-[#d9e2cf] bg-[#f8faf4] p-1">
              <button
                type="button"
                class="rounded-md px-3 py-1.5 text-sm transition"
                :class="language === 'en' ? 'bg-white text-[#23301e]' : 'text-[#66735e] hover:text-[#23301e]'"
                @click="language = 'en'"
              >
                EN
              </button>
              <button
                type="button"
                class="rounded-md px-3 py-1.5 text-sm transition"
                :class="language === 'zh-TW' ? 'bg-white text-[#23301e]' : 'text-[#66735e] hover:text-[#23301e]'"
                @click="language = 'zh-TW'"
              >
                繁中
              </button>
            </div>
          </div>
        </div>

        <p
          v-if="errorMessage"
          class="mt-5 rounded-md border border-[#f2c7c0] bg-[#fff7f6] px-4 py-3 text-sm text-[#a24134]"
        >
          {{ errorMessage }}
        </p>
      </section>

      <div class="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
        <section class="space-y-5">
          <div class="rounded-md border border-[#d9e2cf] bg-white p-5">
            <div class="space-y-4">
              <PathField
                v-model="form.sourceDir"
                :label="t('sourceFolderLabel')"
                :placeholder="t('sourceFolderPlaceholder')"
                :button-label="t('browseButton')"
                :help="t('sourceFolderHelp')"
                :disabled="isBusy"
                @pick="pickDirectory('sourceDir')"
              />

              <PathField
                v-model="form.outputFile"
                :label="t('outputFileLabel')"
                :placeholder="t('outputFilePlaceholder')"
                :button-label="t('saveAsButton')"
                :help="t('outputFileHelp')"
                :disabled="isBusy"
                @pick="pickOutput"
              />

              <PathField
                v-model="form.musicDir"
                :label="t('musicFolderLabel')"
                :placeholder="t('musicFolderPlaceholder')"
                :button-label="t('browseButton')"
                :help="t('musicFolderHelp')"
                :disabled="isBusy"
                @pick="pickDirectory('musicDir')"
              />
            </div>
          </div>

          <OptionPanel
            v-model:options="options"
            :disabled="isBusy"
            :title="t('optionsTitle')"
            :description="t('optionsHelp')"
            :photo-duration-label="t('photoDurationLabel')"
            :photo-duration-help="t('photoDurationHelp')"
            :original-audio-label="t('originalAudioLabel')"
            :original-audio-help="t('originalAudioHelp')"
            :music-volume-label="t('musicVolumeLabel')"
            :music-volume-help="t('musicVolumeHelp')"
          />

          <section class="rounded-md border border-[#d9e2cf] bg-white p-5">
            <div class="flex flex-wrap gap-3">
              <button
                type="button"
                class="min-h-11 rounded-md border border-kiwi-600 bg-kiwi-600 px-4 text-sm font-semibold text-white transition hover:bg-kiwi-800 disabled:cursor-not-allowed disabled:border-[#9fb58c] disabled:bg-[#9fb58c]"
                :disabled="!hasAllInputs || isBusy"
                @click="runStartJob"
              >
                {{ activeAction === 'start' ? t('startingMerge') : t('startMerge') }}
              </button>

              <button
                type="button"
                class="min-h-11 rounded-md border border-kiwi-200 bg-[#f5f8ef] px-4 text-sm font-medium text-kiwi-800 transition hover:border-kiwi-400 hover:bg-kiwi-100 disabled:cursor-not-allowed disabled:border-[#dbe3d0] disabled:bg-[#f4f7ed] disabled:text-[#86937d]"
                :disabled="!hasAllInputs || isBusy"
                @click="runDryRun"
              >
                {{ activeAction === 'dry-run' ? t('runningDryRun') : t('dryRun') }}
              </button>

              <button
                type="button"
                class="min-h-11 rounded-md border border-[#d9e2cf] bg-white px-4 text-sm font-medium text-[#40513a] transition hover:border-kiwi-400 hover:bg-[#f7faf2] disabled:cursor-not-allowed disabled:border-[#dbe3d0] disabled:bg-[#f4f7ed] disabled:text-[#86937d]"
                :disabled="!hasPathInputs || isBusy"
                @click="runScan"
              >
                {{ activeAction === 'scan' ? t('scanningAction') : t('rescan') }}
              </button>

              <button
                type="button"
                class="min-h-11 rounded-md border border-[#f2c7c0] bg-[#fff7f6] px-4 text-sm font-medium text-[#a24134] transition hover:bg-[#fff1ef] disabled:cursor-not-allowed disabled:border-[#ead6d2] disabled:bg-[#fbf3f1] disabled:text-[#c09a92]"
                :disabled="!isRunning || activeAction === 'cancel'"
                @click="runCancel"
              >
                {{ activeAction === 'cancel' ? t('cancelling') : t('cancel') }}
              </button>
            </div>
          </section>
        </section>

        <section class="space-y-5">
          <StatsPanel
            :stats="stats"
            :is-scanning="activeAction === 'scan'"
            :last-scan-label="lastScanLabel"
            :title="t('detectedMediaTitle')"
            :description="t('detectedMediaHelp')"
            :ready-label="t('ready')"
            :scanning-label="t('scanning')"
            :video-label="t('videosLabel')"
            :image-label="t('imagesLabel')"
            :track-label="t('tracksLabel')"
          />
          <ProgressPanel
            :status="jobStatus"
            :job-id="jobId"
            :error="errorMessage"
            :title="t('progressTitle')"
            :description="t('progressHelp')"
            :current-state-label="t('currentStateLabel')"
            :job-id-label="t('jobIdLabel')"
            :not-started-label="t('notStarted')"
            :status-labels="statusLabels"
          />
          <LogPanel
            :logs="logs"
            :title="t('logsTitle')"
            :description="t('logsHelp')"
            :lines-label="t('linesLabel')"
            :empty-label="t('logsEmpty')"
          />
        </section>
      </div>
    </div>
  </main>
</template>
