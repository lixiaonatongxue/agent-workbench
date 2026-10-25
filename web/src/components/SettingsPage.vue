<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const form = ref(null)
const saved = ref(false)
const error = ref('')
const clearing = ref(false)
const cleared = ref(false)

async function load() {
  try {
    form.value = await api.settings()
  } catch (e) {
    error.value = e.message
  }
}

async function save() {
  error.value = ''
  saved.value = false
  try {
    form.value = await api.saveSettings(form.value)
    saved.value = true
    setTimeout(() => (saved.value = false), 2000)
  } catch (e) {
    error.value = e.message
  }
}

async function clearData() {
  if (!confirm('确认清除本地索引数据？（规则文件本身不受影响，仅删除体检索引）')) return
  clearing.value = true
  error.value = ''
  try {
    await api.clearData()
    cleared.value = true
    setTimeout(() => (cleared.value = false), 2000)
  } catch (e) {
    error.value = e.message
  } finally {
    clearing.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-if="form">
    <div class="card">
      <h3>成本估算假设</h3>
      <div class="form-row">
        <label>每天编码 agent 会话数</label>
        <input v-model.number="form.sessions_per_day" type="number" min="1" max="200" />
        <span class="desc">用于年度成本估算</span>
      </div>
      <div class="form-row">
        <label>模型单价（每 1M input tokens）</label>
        <input v-model.number="form.price_per_mtok" type="number" min="0" step="0.5" />
        <input v-model="form.currency" type="text" style="width: 70px;" />
      </div>
      <div class="note" style="border:none;padding:0;margin:0 0 4px;">
        例：Claude Sonnet 输入约 ¥15/1M tokens（以你实际套餐为准）。
      </div>
    </div>

    <div class="card">
      <h3>检测阈值</h3>
      <div class="form-row">
        <label>陈旧阈值（天）</label>
        <input v-model.number="form.stale_days" type="number" min="7" />
        <span class="desc">规则文件超过这么多天未修改 → 疑似过时</span>
      </div>
      <div class="form-row">
        <label>仓库活跃窗口（天）</label>
        <input v-model.number="form.repo_active_days" type="number" min="1" />
        <span class="desc">仅当仓库近期有提交时才标记其过时规则</span>
      </div>
    </div>

    <div class="card">
      <h3>Token 估算系数</h3>
      <div class="form-row">
        <label>中文字符 / token 比</label>
        <input v-model.number="form.cjk_ratio" type="number" min="0.5" step="0.1" />
        <span class="desc">默认 1.8（1 个中文 ≈ 0.56 token）</span>
      </div>
      <div class="form-row">
        <label>其他字符 / token 比</label>
        <input v-model.number="form.other_ratio" type="number" min="0.5" step="0.1" />
        <span class="desc">默认 3.5（英文为主场景）</span>
      </div>
    </div>

    <div style="display:flex;align-items:center;gap:12px;">
      <button class="primary" @click="save">保存设置</button>
      <span v-if="saved" style="color: var(--green);">已保存 ✓</span>
      <span v-if="error" style="color: var(--red);">{{ error }}</span>
    </div>

    <div class="card" style="margin-top: 24px; border-color: rgba(248,81,73,.35);">
      <h3 style="color: var(--red);">危险区</h3>
      <div class="hint" style="margin-bottom: 10px;">
        清除本地索引数据库中的全部扫描结果（规则文件本身不会被改动，设置保留）。
      </div>
      <button class="danger" :disabled="clearing" @click="clearData">
        {{ clearing ? '清除中…' : '清除索引数据' }}
      </button>
      <span v-if="cleared" style="color: var(--green); margin-left: 10px;">已清除 ✓</span>
    </div>
  </div>
</template>
