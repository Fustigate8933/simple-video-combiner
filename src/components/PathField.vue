<script setup lang="ts">
defineProps<{
  label: string
  modelValue: string
  placeholder: string
  buttonLabel: string
  help?: string
  disabled?: boolean
}>()

defineEmits<{
  (event: 'update:modelValue', value: string): void
  (event: 'pick'): void
}>()
</script>

<template>
  <label class="block">
    <span class="mb-2 block text-sm font-medium text-[#304028]">{{ label }}</span>
    <div class="flex gap-3 max-sm:flex-col">
      <input
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        class="min-h-11 w-full rounded-md border border-[#d9e2cf] bg-white px-3 py-2 text-sm text-[#23301e] outline-none transition focus:border-kiwi-400 focus:ring-2 focus:ring-kiwi-100 disabled:cursor-not-allowed disabled:bg-[#f4f7ed] disabled:text-[#86937d]"
        @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      />
      <button
        type="button"
        :disabled="disabled"
        class="min-h-11 shrink-0 rounded-md border border-[#d9e2cf] bg-[#f5f8ef] px-4 text-sm font-medium text-kiwi-800 transition hover:border-kiwi-400 hover:bg-kiwi-100 disabled:cursor-not-allowed disabled:border-[#dbe3d0] disabled:bg-[#f4f7ed] disabled:text-[#86937d] max-sm:w-full"
        @click="$emit('pick')"
      >
        {{ buttonLabel }}
      </button>
    </div>
    <p v-if="help" class="mt-2 text-xs text-[#66735e]">{{ help }}</p>
  </label>
</template>
