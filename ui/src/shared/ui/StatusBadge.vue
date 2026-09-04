<script setup>
import { computed } from 'vue'
import { statusNames } from '../api'

const props = defineProps({
  status: String,
  // роль-специфичные подписи (напр. студенту «assigned» = «На проверке»)
  labels: { type: Object, default: () => ({}) },
})
const label = computed(() => props.labels[props.status] || statusNames[props.status] || props.status)
</script>

<template>
  <span class="status" :class="`status--${status}`"><i />{{ label }}</span>
</template>
