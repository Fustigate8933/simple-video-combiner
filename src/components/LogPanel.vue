<script setup lang="ts">
defineProps<{
  logs: string[]
}>()
</script>

<template>
  <section class="rounded-md border border-[#d9e2cf] bg-white p-5">
    <div class="flex items-center justify-between gap-3">
      <div>
        <p class="text-sm font-semibold text-[#23301e]">Logs</p>
        <p class="mt-1 text-xs text-[#66735e]">Dry-run output, generated command, and live backend job logs.</p>
      </div>
      <span class="rounded-full border border-[#d7dfcc] bg-[#f8faf4] px-3 py-1 text-xs font-medium text-[#66735e]">
        {{ logs.length }} lines
      </span>
    </div>

    <div
      class="mt-4 h-[320px] overflow-auto rounded-md border border-[#dbe3d0] bg-[#1f281b] px-3 py-3 font-mono text-xs leading-5 text-[#dcecc6]"
    >
      <template v-if="logs.length">
        <p v-for="(line, index) in logs" :key="`${index}-${line}`" class="break-words">
          {{ line }}
        </p>
      </template>
      <p v-else class="text-[#9db08b]">Logs will appear here after a scan, dry run, or merge.</p>
    </div>
  </section>
</template>
