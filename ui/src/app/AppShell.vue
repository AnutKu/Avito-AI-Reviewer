<script setup>
import { ref } from 'vue'

const props = defineProps({ user: Object, nav: Array, active: String, notifications: Array })
const emit = defineEmits(['navigate', 'logout', 'read'])
const showNotifications = ref(false)

const roleNames = { student: 'Студент', reviewer: 'Ревьюер', methodist: 'Методист' }
</script>

<template>
  <div class="app-layout">
    <aside class="sidebar">
      <div class="side-brand"><span class="brand-mark brand-mark--small"><b /><b /><b /><b /></span><span>AI Reviewer</span></div>
      <nav>
        <button v-for="item in nav" :key="item.id" :class="{ active: active === item.id || item.pages?.includes(active) }" @click="emit('navigate', item.id)">
          <span class="nav-icon">{{ item.icon }}</span>{{ item.label }}
          <span v-if="item.demo" class="nav-demo">demo</span>
        </button>
      </nav>
      <div class="side-help"><span>?</span><div><b>Нужна помощь?</b><small>Как работает кабинет</small></div></div>
    </aside>
    <section class="workspace">
      <header class="topbar">
        <!-- Здесь стоял «Курс · Аналитика данных · 2026» с кареткой выпадающего
             списка. Переключения курсов нет ни в одной роли, а название было
             зашито в разметку и не совпадало бы с курсом методиста. -->
        <div class="course-switch"><b>AI Reviewer</b></div>
        <div class="top-actions">
          <div class="notification-wrap">
            <button class="icon-button" aria-label="Уведомления" @click="showNotifications = !showNotifications">♢<i v-if="notifications.some(n => !n.read)" /></button>
            <div v-if="showNotifications" class="notification-popover">
              <div class="popover-title"><b>Уведомления</b><span>{{ notifications.filter(n => !n.read).length }} новых</span></div>
              <button v-for="note in notifications" :key="note.id" :class="{ unread: !note.read }" @click="emit('read', note)">
                <i /><span><b>{{ note.title }}</b><small>{{ note.body }}</small></span>
              </button>
              <div v-if="!notifications.length" class="empty-mini">Новых уведомлений нет</div>
            </div>
          </div>
          <div class="profile"><span>{{ user.name.split(' ').map(x => x[0]).slice(0,2).join('') }}</span><div><b>{{ user.name }}</b><small>{{ roleNames[user.role] }}</small></div></div>
          <button class="logout" title="Выйти" @click="emit('logout')">↗</button>
        </div>
      </header>
      <main class="page"><slot /></main>
    </section>
  </div>
</template>
