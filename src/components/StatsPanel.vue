<script setup lang="ts">
import type { ScanResponse } from '../lib/api'

defineProps<{
  stats: ScanResponse | null
  isScanning?: boolean
  lastScanLabel?: string
}>()

const statCards = [
  { key: 'mp4_count', label: 'Videos' },
  { key: 'image_count', label: 'Images' },
  { key: 'music_count', label: 'Tracks' },
] as const
</script>

<template>
  <section class="rounded-md border border-[#d9e2cf] bg-white p-5">
    <div class="flex items-center justify-between gap-3">
      <div>
        <p class="text-sm font-semibold text-[#23301e]">Detected media</p>
        <p class="mt-1 text-xs text-[#66735e]">Counts update from the selected source and music folders.</p>
      </div>
      <span
        class="rounded-full border px-3 py-1 text-xs font-medium"
        :class="isScanning ? 'border-kiwi-200 bg-kiwi-50 text-kiwi-800' : 'border-[#d7dfcc] bg-[#f8faf4] text-[#66735e]'"
      >
        {{ isScanning ? 'Scanning' : 'Ready' }}
      </span>
    </div>

    <div class="mt-4 grid grid-cols-3 gap-3">
      <div
        v-for="card in statCards"
        :key="card.key"
        class="rounded-md border border-[#e0e7d7] bg-white px-3 py-4"
      >
        <p class="text-xs font-medium uppercase tracking-wide text-[#66735e]">{{ card.label }}</p>
        <p class="mt-2 text-2xl font-semibold text-[#23301e]">
          {{ stats ? stats[card.key] : '—' }}
        </p>
      </div>
    </div>

    <p class="mt-4 text-xs text-[#66735e]">
      {{ lastScanLabel ?? 'Run a scan after choosing your folders.' }}
    </p>
  </section>
</template>
