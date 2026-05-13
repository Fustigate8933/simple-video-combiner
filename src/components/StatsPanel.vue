<script setup lang="ts">
import type { ScanResponse } from '../lib/api'

defineProps<{
  stats: ScanResponse | null
  isScanning?: boolean
  lastScanLabel?: string
  title: string
  description: string
  readyLabel: string
  scanningLabel: string
  videoLabel: string
  imageLabel: string
  trackLabel: string
}>()
</script>

<template>
  <section class="rounded-md border border-[#d9e2cf] bg-white p-5">
    <div class="flex items-center justify-between gap-3">
      <div>
        <p class="text-sm font-semibold text-[#23301e]">{{ title }}</p>
        <p class="mt-1 text-xs text-[#66735e]">{{ description }}</p>
      </div>
      <span
        class="rounded-full border px-3 py-1 text-xs font-medium"
        :class="isScanning ? 'border-kiwi-200 bg-kiwi-50 text-kiwi-800' : 'border-[#d7dfcc] bg-[#f8faf4] text-[#66735e]'"
      >
        {{ isScanning ? scanningLabel : readyLabel }}
      </span>
    </div>

    <div class="mt-4 grid grid-cols-3 gap-3">
      <div class="rounded-md border border-[#e0e7d7] bg-white px-3 py-4">
        <p class="text-xs font-medium uppercase tracking-wide text-[#66735e]">{{ videoLabel }}</p>
        <p class="mt-2 text-2xl font-semibold text-[#23301e]">
          {{ stats ? stats.mp4_count : '—' }}
        </p>
      </div>
      <div class="rounded-md border border-[#e0e7d7] bg-white px-3 py-4">
        <p class="text-xs font-medium uppercase tracking-wide text-[#66735e]">{{ imageLabel }}</p>
        <p class="mt-2 text-2xl font-semibold text-[#23301e]">
          {{ stats ? stats.image_count : '—' }}
        </p>
      </div>
      <div class="rounded-md border border-[#e0e7d7] bg-white px-3 py-4">
        <p class="text-xs font-medium uppercase tracking-wide text-[#66735e]">{{ trackLabel }}</p>
        <p class="mt-2 text-2xl font-semibold text-[#23301e]">
          {{ stats ? stats.music_count : '—' }}
        </p>
      </div>
    </div>

    <p class="mt-4 text-xs text-[#66735e]">
      {{ lastScanLabel ?? 'Run a scan after choosing your folders.' }}
    </p>
  </section>
</template>
