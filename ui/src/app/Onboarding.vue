<script setup>
// Первое знакомство с кабинетом: короткая проводка по шагам, своя для каждой
// роли. Показывается один раз, дальше открывается вручную из блока «Нужна
// помощь?» — поэтому закрытие здесь всегда честное, без «напомнить позже».
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { stepsFor, titleFor } from '../shared/onboarding'

const props = defineProps({ role: String })
const emit = defineEmits(['close'])

const index = ref(0)
const steps = computed(() => stepsFor(props.role))
const step = computed(() => steps.value[index.value] || [])
const last = computed(() => index.value >= steps.value.length - 1)
const primary = ref(null)

function next() { if (last.value) emit('close'); else index.value += 1 }
function back() { if (index.value > 0) index.value -= 1 }

// Клавиатура: Escape закрывает, стрелки листают. Модальное окно, которое
// невозможно закрыть с клавиатуры, — ловушка для тех, кто не пользуется мышью.
function onKey(event) {
  if (event.key === 'Escape') emit('close')
  else if (event.key === 'ArrowRight') next()
  else if (event.key === 'ArrowLeft') back()
}

onMounted(() => { window.addEventListener('keydown', onKey); primary.value?.focus() })
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="onb-backdrop" @click.self="emit('close')">
    <div class="onb-card" role="dialog" aria-modal="true" :aria-label="titleFor(role)">
      <header>
        <span class="brand-mark brand-mark--small"><b /><b /><b /><b /></span>
        <div><small>Знакомство</small><b>{{ titleFor(role) }}</b></div>
        <button class="onb-close" aria-label="Закрыть" @click="emit('close')">✕</button>
      </header>

      <div class="onb-body">
        <span class="onb-icon">{{ step[0] }}</span>
        <h2>{{ step[1] }}</h2>
        <p>{{ step[2] }}</p>
      </div>

      <div class="onb-dots">
        <button
          v-for="(s, i) in steps" :key="i" :class="{ on: i === index }"
          :aria-label="`Шаг ${i + 1}: ${s[1]}`" @click="index = i" />
      </div>

      <footer>
        <button class="ghost" @click="emit('close')">Пропустить</button>
        <div>
          <button v-if="index" class="ghost" @click="back">Назад</button>
          <button ref="primary" class="onb-next" @click="next">
            {{ last ? 'Начать работу' : 'Далее' }}
          </button>
        </div>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.onb-backdrop { position: fixed; inset: 0; z-index: 80; display: grid; place-items: center; padding: 20px; background: rgba(23,26,40,.5); backdrop-filter: blur(3px); animation: onb-in .18s ease; }
.onb-card { width: 100%; max-width: 520px; background: var(--surface); border-radius: 24px; overflow: hidden; box-shadow: 0 30px 80px rgba(23,26,40,.34); animation: onb-up .22s ease; }

header { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 14px; padding: 20px 22px; color: #fff; background: linear-gradient(115deg, #241f3d, #1a2b4d 55%, #0f3b63); }
header small { display: block; color: #a9b4cd; font-size: var(--fs-3xs); letter-spacing: .14em; text-transform: uppercase; font-weight: 800; }
header b { display: block; font-size: var(--fs-lg); margin-top: 4px; }
.onb-close { border: 0; background: rgba(255,255,255,.12); color: #fff; width: 30px; height: 30px; border-radius: 50%; cursor: pointer; font-size: var(--fs-xs); }
.onb-close:hover { background: rgba(255,255,255,.22); }

.onb-body { padding: 30px 30px 6px; text-align: center; }
.onb-icon { display: grid; place-items: center; width: 62px; height: 62px; margin: 0 auto 18px; border-radius: 20px; font-size: var(--fs-4xl); background: linear-gradient(150deg, #eef4ff, #f5ecff); }
.onb-body h2 { font-size: var(--fs-2xl); letter-spacing: -.02em; margin: 0 0 10px; }
.onb-body p { margin: 0; color: var(--muted); font-size: var(--fs-md); line-height: 1.65; }

.onb-dots { display: flex; justify-content: center; gap: 7px; padding: 24px 0 20px; }
.onb-dots button { width: 7px; height: 7px; padding: 0; border: 0; border-radius: 10px; background: #dcdde5; cursor: pointer; transition: .2s ease; }
.onb-dots button.on { width: 22px; background: var(--blue); }

footer { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 16px 22px; border-top: 1px solid var(--line); background: #fbfbfd; }
footer > div { display: flex; gap: 8px; }
.ghost { border: 0; background: none; color: var(--muted); font-size: var(--fs-sm); font-weight: 600; padding: 10px 12px; border-radius: 10px; cursor: pointer; }
.ghost:hover { background: #f0f1f5; color: var(--ink); }
.onb-next { border: 0; border-radius: 11px; background: var(--ink); color: #fff; font-size: var(--fs-sm); font-weight: 700; padding: 11px 20px; cursor: pointer; }
.onb-next:hover { background: #2c2f42; }

@keyframes onb-in { from { opacity: 0 } }
@keyframes onb-up { from { opacity: 0; transform: translateY(14px) } }

/* Анимация — украшение. Тем, кто её отключил в системе, она мешает. */
@media (prefers-reduced-motion: reduce) { .onb-backdrop, .onb-card { animation: none } }

@media (max-width: 560px) { .onb-body { padding: 24px 20px 4px } .onb-body h2 { font-size: var(--fs-xl) } }
</style>
