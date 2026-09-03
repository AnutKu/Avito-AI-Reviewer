<script setup>
defineProps({ loading: Boolean, error: String })
defineEmits(['login'])

const roles = [
  { id: 'student', title: 'Студент', text: 'Сдать работу и получить обратную связь', color: 'blue', icon: 'С' },
  { id: 'reviewer', title: 'Ревьюер', text: 'Проверить очередь и принять решения', color: 'purple', icon: 'Р' },
  { id: 'methodist', title: 'Методист', text: 'Управлять курсом и распределением', color: 'green', icon: 'М' },
]
</script>

<template>
  <main class="login-page">
    <div class="login-brand"><span class="brand-mark"><b /><b /><b /><b /></span><span>Avito Education</span></div>
    <section class="login-card">
      <div class="login-copy">
        <span class="eyebrow">AI REVIEWER</span>
        <h1>Единый кабинет<br />проверки работ</h1>
        <p>Распределение, предварительное AI-ревью и обратная связь — в одном понятном процессе.</p>
        <div class="login-art">
          <div class="art-card art-card--one"><span>24</span><small>работы</small></div>
          <div class="art-card art-card--two"><span>84%</span><small>согласие</small></div>
          <div class="art-orbit"><i /><i /><i /></div>
        </div>
      </div>
      <div class="login-actions">
        <div><span class="overline">ДЕМО-ВХОД</span><h2>Выберите роль</h2><p>Пароль не потребуется</p></div>
        <button v-for="role in roles" :key="role.id" class="role-button" :disabled="loading" @click="$emit('login', role.id)">
          <span class="role-icon" :class="`role-icon--${role.color}`">{{ role.icon }}</span>
          <span><b>{{ role.title }}</b><small>{{ role.text }}</small></span>
          <strong>→</strong>
        </button>
        <p v-if="error" class="form-error">{{ error }}</p>
        <small class="login-note">В системе используются учебные и демонстрационные данные</small>
      </div>
    </section>
  </main>
</template>
