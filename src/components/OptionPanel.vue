<script setup lang="ts">
export interface MergeFormOptions {
  photoDuration: number
  originalVolume: number
  musicVolume: number
}

const props = defineProps<{
  options: MergeFormOptions
  disabled?: boolean
}>()

const emit = defineEmits<{
  (event: 'update:options', value: MergeFormOptions): void
}>()

function updateOption<K extends keyof MergeFormOptions>(key: K, value: string) {
  const parsed = Number.parseFloat(value)
  emit('update:options', {
    ...props.options,
    [key]: Number.isFinite(parsed) ? parsed : 0,
  })
}
</script>

<template>
  <section class="rounded-md border border-[#d9e2cf] bg-white p-5">
    <div class="flex items-start justify-between gap-3">
      <div>
        <p class="text-sm font-semibold text-[#23301e]">Merge options</p>
        <p class="mt-1 text-xs text-[#66735e]">Keep the defaults unless you need a different pace or mix.</p>
      </div>
    </div>

    <div class="mt-4 grid gap-4 sm:grid-cols-3">
      <label class="block">
        <span class="mb-2 block text-xs font-medium uppercase tracking-wide text-[#66735e]">
          Photo duration
        </span>
        <input
          :value="options.photoDuration"
          :disabled="disabled"
          type="number"
          min="0.1"
          step="0.1"
          class="min-h-11 w-full rounded-md border border-[#d9e2cf] bg-white px-3 py-2 text-sm text-[#23301e] outline-none transition focus:border-kiwi-400 focus:ring-2 focus:ring-kiwi-100 disabled:cursor-not-allowed disabled:bg-[#f4f7ed]"
          @input="updateOption('photoDuration', ($event.target as HTMLInputElement).value)"
        />
        <p class="mt-2 text-xs text-[#66735e]">Seconds shown for each still image.</p>
      </label>

      <label class="block">
        <span class="mb-2 block text-xs font-medium uppercase tracking-wide text-[#66735e]">
          Original audio
        </span>
        <input
          :value="options.originalVolume"
          :disabled="disabled"
          type="number"
          min="0"
          max="1"
          step="0.05"
          class="min-h-11 w-full rounded-md border border-[#d9e2cf] bg-white px-3 py-2 text-sm text-[#23301e] outline-none transition focus:border-kiwi-400 focus:ring-2 focus:ring-kiwi-100 disabled:cursor-not-allowed disabled:bg-[#f4f7ed]"
          @input="updateOption('originalVolume', ($event.target as HTMLInputElement).value)"
        />
        <p class="mt-2 text-xs text-[#66735e]">Volume level for the source clips.</p>
      </label>

      <label class="block">
        <span class="mb-2 block text-xs font-medium uppercase tracking-wide text-[#66735e]">
          Music volume
        </span>
        <input
          :value="options.musicVolume"
          :disabled="disabled"
          type="number"
          min="0"
          max="1"
          step="0.05"
          class="min-h-11 w-full rounded-md border border-[#d9e2cf] bg-white px-3 py-2 text-sm text-[#23301e] outline-none transition focus:border-kiwi-400 focus:ring-2 focus:ring-kiwi-100 disabled:cursor-not-allowed disabled:bg-[#f4f7ed]"
          @input="updateOption('musicVolume', ($event.target as HTMLInputElement).value)"
        />
        <p class="mt-2 text-xs text-[#66735e]">Background music mix level.</p>
      </label>
    </div>
  </section>
</template>
