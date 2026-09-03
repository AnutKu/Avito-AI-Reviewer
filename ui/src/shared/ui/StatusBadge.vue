<script setup>
import { statusNames } from '../api'
defineProps({ status: String })
</script>

<template>
  <span class="status" :class="`status--${status}`"><i />{{ statusNames[status] || status }}</span>
</template>
