<script setup lang="ts">
export interface MergeFormOptions {
  photoDuration: number
  originalVolume: number
  musicVolume: number
}

const props = defineProps<{
  options: MergeFormOptions
  disabled?: boolean
  title: string
  description: string
  photoDurationLabel: string
  photoDurationHelp: string
  originalAudioLabel: string
  originalAudioHelp: string
  musicVolumeLabel: string
  musicVolumeHelp: string
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
        <p class="text-sm font-semibold text-[#23301e]">{{ title }}</p>
        <p class="mt-1 text-xs text-[#66735e]">{{ description }}</p>
      </div>
    </div>

    <div class="mt-4 grid gap-4 sm:grid-cols-3">
      <label class="block">
        <span class="mb-2 block text-xs font-medium uppercase tracking-wide text-[#66735e]">
          {{ photoDurationLabel }}
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
        <p class="mt-2 text-xs text-[#66735e]">{{ photoDurationHelp }}</p>
      </label>

      <label class="block">
        <span class="mb-2 block text-xs font-medium uppercase tracking-wide text-[#66735e]">
          {{ originalAudioLabel }}
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
        <p class="mt-2 text-xs text-[#66735e]">{{ originalAudioHelp }}</p>
      </label>

      <label class="block">
        <span class="mb-2 block text-xs font-medium uppercase tracking-wide text-[#66735e]">
          {{ musicVolumeLabel }}
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
        <p class="mt-2 text-xs text-[#66735e]">{{ musicVolumeHelp }}</p>
      </label>
    </div>
  </section>
</template>
