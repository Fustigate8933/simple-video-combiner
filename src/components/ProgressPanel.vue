<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  status: string
  jobId?: string | null
  error?: string | null
}>()

const statusMap: Record<string, { label: string; tone: string; width: string }> = {
  idle: { label: 'Idle', tone: 'bg-[#eff4e5] text-[#5e6d54] border-[#d7dfcc]', width: '0%' },
  pending: { label: 'Preparing', tone: 'bg-kiwi-50 text-kiwi-800 border-kiwi-200', width: '14%' },
  running: { label: 'Running ffmpeg', tone: 'bg-kiwi-50 text-kiwi-800 border-kiwi-200', width: '72%' },
  succeeded: { label: 'Completed', tone: 'bg-[#eef8db] text-kiwi-800 border-kiwi-200', width: '100%' },
  failed: { label: 'Failed', tone: 'bg-[#fff3f1] text-[#a24134] border-[#f2c7c0]', width: '100%' },
  cancelled: { label: 'Cancelled', tone: 'bg-[#f7f4ea] text-[#8a6a2f] border-[#ead8a8]', width: '100%' },
}

const current = computed(() => statusMap[props.status] ?? statusMap.idle)
</script>

<template>
  <section class="rounded-md border border-[#d9e2cf] bg-white p-5">
    <div class="flex items-start justify-between gap-3">
      <div>
        <p class="text-sm font-semibold text-[#23301e]">Progress</p>
        <p class="mt-1 text-xs text-[#66735e]">Live job state from the backend event stream.</p>
      </div>
      <span class="rounded-full border px-3 py-1 text-xs font-medium" :class="current.tone">
        {{ current.label }}
      </span>
    </div>

    <div class="mt-4">
      <div class="h-2.5 overflow-hidden rounded-full bg-[#edf2e4]">
        <div
          class="h-full rounded-full bg-kiwi-400 transition-all duration-300"
          :class="status === 'running' ? 'animate-pulse' : ''"
          :style="{ width: current.width }"
        />
      </div>
    </div>

    <dl class="mt-4 grid gap-3 text-sm text-[#40513a] sm:grid-cols-2">
      <div class="rounded-md border border-[#e0e7d7] bg-white px-3 py-3">
        <dt class="text-xs font-medium uppercase tracking-wide text-[#66735e]">Current state</dt>
        <dd class="mt-1 font-medium">{{ current.label }}</dd>
      </div>
      <div class="rounded-md border border-[#e0e7d7] bg-white px-3 py-3">
        <dt class="text-xs font-medium uppercase tracking-wide text-[#66735e]">Job ID</dt>
        <dd class="mt-1 break-all font-medium">{{ jobId ?? 'Not started' }}</dd>
      </div>
    </dl>

    <p
      v-if="error"
      class="mt-4 rounded-md border border-[#f2c7c0] bg-[#fff7f6] px-3 py-2 text-sm text-[#a24134]"
    >
      {{ error }}
    </p>
  </section>
</template>
