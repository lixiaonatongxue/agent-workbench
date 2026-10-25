<script setup>
import { ref } from 'vue'
import DoctorPage from './components/DoctorPage.vue'
import SessionsPage from './components/SessionsPage.vue'
import SettingsPage from './components/SettingsPage.vue'

const tab = ref('doctor')
const tabs = [
  { id: 'doctor', label: '规则体检' },
  { id: 'sessions', label: '会话档案馆' },
  { id: 'settings', label: '设置' },
]
</script>

<template>
  <div class="topbar">
    <div class="topbar-inner">
      <div class="logo">
        <span class="mark">🛠</span>
        <span>Agent Workbench
          <span class="sub">编码 agent 的体检台 + 档案馆 · 100% 本地</span>
        </span>
      </div>
      <div class="tabs">
        <button
          v-for="t in tabs" :key="t.id"
          class="tab" :class="{ active: tab === t.id }"
          @click="tab = t.id"
        >{{ t.label }}</button>
      </div>
    </div>
  </div>
  <div class="container">
    <DoctorPage v-show="tab === 'doctor'" />
    <SessionsPage v-if="tab === 'sessions'" />
    <SettingsPage v-if="tab === 'settings'" />
  </div>
</template>
