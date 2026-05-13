<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref } from 'vue'

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

const form = reactive({
  sourceDir: '',
  outputFile: '',
  musicDir: '',
  photoDuration: 7,
  originalVolume: 0.2,
  musicVolume: 0.85,
})

const stats = ref<ScanResponse | null>(null)
const logs = ref<string[]>([])
const uiMessage = ref('Choose your folders, scan them, then start the merge.')
const lastScanLabel = ref('Run a scan after choosing your folders.')
const errorMessage = ref<string | null>(null)
const activeAction = ref<'scan' | 'dry-run' | 'start' | 'cancel' | null>(null)
const jobId = ref<string | null>(null)
const jobStatus = ref('idle')
const subscription = ref<JobSubscription | null>(null)

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
        uiMessage.value = 'Merge completed.'
      } else if (status === 'failed') {
        uiMessage.value = 'Merge failed.'
      } else if (status === 'cancelled') {
        uiMessage.value = 'Merge cancelled.'
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

      const message = error instanceof ApiError ? error.detail : 'Live job updates stopped unexpectedly'
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
    errorMessage.value = 'Source and music directories are required before scanning.'
    return
  }

  errorMessage.value = null
  activeAction.value = 'scan'

  try {
    const response = await scan(form.sourceDir.trim(), form.musicDir.trim())
    stats.value = response
    lastScanLabel.value = `Found ${response.mp4_count} videos, ${response.image_count} images, ${response.music_count} tracks.`
    uiMessage.value = 'Scan complete.'
    appendLog(
      `Scan complete: ${response.mp4_count} videos, ${response.image_count} images, ${response.music_count} tracks.`,
    )
  } catch (error) {
    handleError(error, 'Scan failed')
  } finally {
    activeAction.value = null
  }
}

async function runDryRun() {
  if (!hasAllInputs.value) {
    errorMessage.value = 'Source, output, and music paths are required before a dry run.'
    return
  }

  errorMessage.value = null
  activeAction.value = 'dry-run'

  try {
    const response = await dryRun(toMergeOptions())
    stats.value = response.summary
    lastScanLabel.value = `Dry run checked ${response.summary.mp4_count} videos, ${response.summary.image_count} images, ${response.summary.music_count} tracks.`
    uiMessage.value = 'Dry run complete.'
    pushLogs([
      'Dry run',
      ...response.messages,
      `Command: ${response.command_text}`,
    ])
  } catch (error) {
    handleError(error, 'Dry run failed')
  } finally {
    activeAction.value = null
  }
}

async function runStartJob() {
  if (!hasAllInputs.value) {
    errorMessage.value = 'Source, output, and music paths are required before starting a merge.'
    return
  }

  errorMessage.value = null
  activeAction.value = 'start'
  logs.value = []

  try {
    const response = await startJob(toMergeOptions())
    setJobState(response)
    uiMessage.value = 'Merge started.'
    startSubscription(response.job_id)
  } catch (error) {
    handleError(error, 'Merge failed to start')
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
    uiMessage.value = response.status === 'cancelled' ? 'Merge cancelled.' : 'Cancellation requested.'
  } catch (error) {
    handleError(error, 'Unable to cancel the active merge')
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
            <h1 class="mt-2 text-2xl font-semibold sm:text-3xl">Video merge control panel</h1>
            <p class="mt-2 max-w-2xl text-sm text-[#66735e]">{{ uiMessage }}</p>
          </div>
          <!-- <div class="flex shrink-0 items-center gap-3 self-start"> -->
          <!--   <span -->
          <!--     class="inline-flex min-h-11 items-center rounded-full border px-4 text-sm font-medium" -->
          <!--     :class=" -->
          <!--       isRunning -->
          <!--         ? 'border-kiwi-200 bg-kiwi-50 text-kiwi-800' -->
          <!--         : 'border-[#d7dfcc] bg-[#f8faf4] text-[#66735e]' -->
          <!--     " -->
          <!--   > -->
          <!--     {{ isRunning ? 'Merge running' : 'Ready' }} -->
          <!--   </span> -->
          <!-- </div> -->
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
                label="Source folder"
                placeholder="/path/to/source-media"
                button-label="Browse"
                help="Choose the folder with videos and still images."
                :disabled="isBusy"
                @pick="pickDirectory('sourceDir')"
              />

              <PathField
                v-model="form.outputFile"
                label="Output MP4"
                placeholder="/path/to/output.mp4"
                button-label="Save as"
                help="Pick the final merged MP4 destination."
                :disabled="isBusy"
                @pick="pickOutput"
              />

              <PathField
                v-model="form.musicDir"
                label="Music folder"
                placeholder="/path/to/music"
                button-label="Browse"
                help="Kiwi Merge scans this folder for MP3 tracks."
                :disabled="isBusy"
                @pick="pickDirectory('musicDir')"
              />
            </div>
          </div>

          <OptionPanel v-model:options="options" :disabled="isBusy" />

          <section class="rounded-md border border-[#d9e2cf] bg-white p-5">
            <div class="flex flex-wrap gap-3">
              <button
                type="button"
                class="min-h-11 rounded-md border border-kiwi-600 bg-kiwi-600 px-4 text-sm font-semibold text-white transition hover:bg-kiwi-800 disabled:cursor-not-allowed disabled:border-[#9fb58c] disabled:bg-[#9fb58c]"
                :disabled="!hasAllInputs || isBusy"
                @click="runStartJob"
              >
                {{ activeAction === 'start' ? 'Starting...' : 'Start merge' }}
              </button>

              <button
                type="button"
                class="min-h-11 rounded-md border border-kiwi-200 bg-[#f5f8ef] px-4 text-sm font-medium text-kiwi-800 transition hover:border-kiwi-400 hover:bg-kiwi-100 disabled:cursor-not-allowed disabled:border-[#dbe3d0] disabled:bg-[#f4f7ed] disabled:text-[#86937d]"
                :disabled="!hasAllInputs || isBusy"
                @click="runDryRun"
              >
                {{ activeAction === 'dry-run' ? 'Running dry run...' : 'Dry run' }}
              </button>

              <button
                type="button"
                class="min-h-11 rounded-md border border-[#d9e2cf] bg-white px-4 text-sm font-medium text-[#40513a] transition hover:border-kiwi-400 hover:bg-[#f7faf2] disabled:cursor-not-allowed disabled:border-[#dbe3d0] disabled:bg-[#f4f7ed] disabled:text-[#86937d]"
                :disabled="!hasPathInputs || isBusy"
                @click="runScan"
              >
                {{ activeAction === 'scan' ? 'Scanning...' : 'Rescan' }}
              </button>

              <button
                type="button"
                class="min-h-11 rounded-md border border-[#f2c7c0] bg-[#fff7f6] px-4 text-sm font-medium text-[#a24134] transition hover:bg-[#fff1ef] disabled:cursor-not-allowed disabled:border-[#ead6d2] disabled:bg-[#fbf3f1] disabled:text-[#c09a92]"
                :disabled="!isRunning || activeAction === 'cancel'"
                @click="runCancel"
              >
                {{ activeAction === 'cancel' ? 'Cancelling...' : 'Cancel' }}
              </button>
            </div>
          </section>
        </section>

        <section class="space-y-5">
          <StatsPanel
            :stats="stats"
            :is-scanning="activeAction === 'scan'"
            :last-scan-label="lastScanLabel"
          />
          <ProgressPanel :status="jobStatus" :job-id="jobId" :error="errorMessage" />
          <LogPanel :logs="logs" />
        </section>
      </div>
    </div>
  </main>
</template>
