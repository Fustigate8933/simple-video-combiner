<script setup lang="ts">
defineProps<{
  logs: string[]
  title: string
  description: string
  linesLabel: string
  emptyLabel: string
}>()
</script>

<template>
  <section class="rounded-md border border-[#d9e2cf] bg-white p-5">
    <div class="flex items-center justify-between gap-3">
      <div>
        <p class="text-sm font-semibold text-[#23301e]">{{ title }}</p>
        <p class="mt-1 text-xs text-[#66735e]">{{ description }}</p>
      </div>
      <span class="rounded-full border border-[#d7dfcc] bg-[#f8faf4] px-3 py-1 text-xs font-medium text-[#66735e]">
        {{ logs.length }} {{ linesLabel }}
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
      <p v-else class="text-[#9db08b]">{{ emptyLabel }}</p>
    </div>
  </section>
</template>
