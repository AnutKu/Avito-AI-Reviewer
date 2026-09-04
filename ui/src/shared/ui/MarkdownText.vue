<script setup>
import { computed } from 'vue'

import { renderInline, renderMarkdown } from '../markdown'

// Единственное место в кабинете, где используется v-html. Безопасность держится
// не на этом компоненте, а на markdown.js: туда попадает текст, оттуда выходит
// разметка из белого списка, и сырой HTML через неё не проходит. Всё остальное
// в интерфейсе выводится через {{ }} и остаётся текстом.
const props = defineProps({
  text: { type: String, default: '' },
  // Без блоков: для подписи или строки, которая живёт внутри чужой вёрстки.
  inline: { type: Boolean, default: false },
})

const html = computed(() =>
  props.inline ? renderInline(props.text) : renderMarkdown(props.text),
)
</script>

<template>
  <span v-if="inline" class="md" v-html="html" />
  <div v-else-if="html" class="md" v-html="html" />
</template>
