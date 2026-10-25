<script setup>
import { onMounted, onUnmounted, ref, computed } from 'vue'
import { api } from '../api'

const rootsInput = ref(localStorage.getItem('aw.roots') || '')
const includeGlobal = ref(true)
const scanning = ref(false)
const status = ref(null)
const report = ref(null)
const error = ref('')
let timer = null

const rootsList = computed(() =>
  rootsInput.value.split(/[;；,，\n]/).map(s => s.trim()).filter(Boolean))

const fmt = (n) => (n ?? 0).toLocaleString('zh-CN')
const shortDate = (iso) => iso ? iso.slice(0, 10) : ''

const progressPercent = computed(() => {
  const st = status.value
  if (!st || !st.total) return st && st.phase === 'done' ? 100 : 0
  return Math.round((st.done / st.total) * 100)
})

async function startScan() {
  error.value = ''
  if (!rootsList.value.length) {
    error.value = '请先填写要扫描的根目录'
    return
  }
  localStorage.setItem('aw.roots', rootsInput.value)
  try {
    await api.startScan(rootsList.value, includeGlobal.value)
    scanning.value = true
    poll()
  } catch (e) {
    error.value = e.message
  }
}

function poll() {
  clearInterval(timer)
  timer = setInterval(async () => {
    try {
      const st = await api.scanStatus()
      status.value = st
      if (!st.running) {
        clearInterval(timer)
        scanning.value = false
        if (st.error) error.value = st.error
        await loadReport()
      }
    } catch (e) {
      clearInterval(timer)
      scanning.value = false
      error.value = e.message
    }
  }, 700)
}

async function loadReport() {
  const r = await api.report()
  report.value = r
}

onMounted(async () => {
  try { await loadReport() } catch { /* no scan yet */ }
})
onUnmounted(() => clearInterval(timer))

const totals = computed(() => report.value?.totals ?? { files: 0, tokens: 0 })
const cost = computed(() => report.value?.cost ?? {})
const dups = computed(() => report.value?.duplicates ?? { groups: [], group_count: 0 })
const staleFiles = computed(() => report.value?.stale_files ?? [])
</script>

<template>
  <!-- scan bar -->
  <div class="card">
    <h3>扫描</h3>
    <div class="scan-bar">
      <input
        v-model="rootsInput" type="text"
        placeholder="项目根目录，多个用逗号分隔，例如 D:\projects"
        :disabled="scanning"
      />
      <label class="hint" style="display:flex;align-items:center;gap:6px;white-space:nowrap;">
        <input v-model="includeGlobal" type="checkbox" :disabled="scanning" />
        含用户目录全局规则
      </label>
      <button class="primary" :disabled="scanning" @click="startScan">
        {{ scanning ? '扫描中…' : '开始体检' }}
      </button>
    </div>
    <div v-if="scanning || status?.running" class="progress-track">
      <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
    </div>
    <div v-if="status" class="progress-msg">
      {{ status.phase }} · {{ status.done }}/{{ status.total }} · {{ status.message }}
    </div>
    <div v-if="error" style="color: var(--red); margin-top: 8px;">{{ error }}</div>
  </div>

  <div v-if="!report || !report.totals?.files" class="card empty">
    还没有体检数据 —— 填写根目录点「开始体检」，或先去「设置」调整单价假设。
  </div>

  <template v-if="report?.totals?.files">
    <!-- headline stats -->
    <div class="stat-grid">
      <div class="stat">
        <div class="label">规则文件</div>
        <div class="value">{{ fmt(totals.files) }} 个</div>
        <div class="foot">覆盖 {{ report.repos_scanned }} 个仓库</div>
      </div>
      <div class="stat">
        <div class="label">规则总量</div>
        <div class="value">≈ {{ fmt(totals.tokens) }} <span style="font-size:13px;color:var(--muted)">tokens</span></div>
        <div class="foot">{{ fmt(totals.lines) }} 行 / {{ fmt(totals.chars) }} 字符</div>
      </div>
      <div class="stat">
        <div class="label">最大单会话注入</div>
        <div class="value" :class="totals.tokens > 20000 ? 'bad' : totals.tokens > 8000 ? 'warn' : 'good'">
          ≈ {{ fmt(cost.worst_session_tokens) }}
        </div>
        <div class="foot">{{ cost.worst_agent }} · 每次会话都烧</div>
      </div>
      <div class="stat">
        <div class="label">估算年度成本</div>
        <div class="value" :class="cost.worst_year_cost > 200 ? 'warn' : ''">
          {{ cost.currency === 'CNY' ? '¥' : '' }}{{ fmt(cost.worst_year_cost) }}
        </div>
        <div class="foot">按 {{ cost.sessions_per_day }} 会话/天 · {{ cost.price_per_mtok }}/{{ cost.currency }}/1M tokens</div>
      </div>
      <div class="stat">
        <div class="label">重复规则浪费</div>
        <div class="value" :class="dups.wasted_tokens > 0 ? 'warn' : 'good'">
          ≈ {{ fmt(dups.wasted_tokens) }}
        </div>
        <div class="foot">{{ dups.group_count }} 组疑似重复 · 年浪费 ¥{{ fmt(cost.duplicate_year_cost) }}</div>
      </div>
    </div>

    <!-- per agent -->
    <div class="section-title">按 Agent</div>
    <div class="card" style="padding: 6px 12px;">
      <table>
        <thead>
          <tr>
            <th>Agent</th><th class="num">全局注入 / 会话</th><th class="num">覆盖仓库</th>
            <th class="num">最重仓库注入</th><th class="num">最大会话注入</th><th>最重仓库</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in report.per_agent" :key="a.id">
            <td>{{ a.name }}</td>
            <td class="num">{{ fmt(a.global_tokens) }}</td>
            <td class="num">{{ a.repo_count }}</td>
            <td class="num">{{ fmt(a.max_repo_tokens) }}</td>
            <td class="num"><b>{{ fmt(a.max_session_injection) }}</b></td>
            <td class="path-cell">{{ a.max_repo || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- per repo -->
    <div class="section-title">按仓库</div>
    <div class="card" style="padding: 6px 12px;">
      <table>
        <thead>
          <tr><th>仓库</th><th>最近活动</th><th>各 agent 注入</th><th class="num">合计</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in report.per_repo" :key="r.repo">
            <td class="path-cell" :title="r.repo">{{ r.name || r.repo }}</td>
            <td>{{ shortDate(r.last_activity) || '—' }}</td>
            <td>
              <span v-for="(t, agent) in r.tokens_by_agent" :key="agent" class="chip agent">
                {{ agent }} ≈{{ fmt(t) }}
              </span>
            </td>
            <td class="num"><b>{{ fmt(r.total_tokens) }}</b></td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- files -->
    <div class="section-title">文件明细 <span class="count">{{ report.files.length }} 个文件</span></div>
    <div class="card" style="padding: 6px 12px;">
      <table>
        <thead>
          <tr>
            <th>文件</th><th>Agents</th><th>仓库</th>
            <th class="num">行数</th><th class="num">≈ tokens</th><th>最后修改</th><th>状态</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="f in report.files" :key="f.path">
            <td class="path-cell" :title="f.path">{{ f.path }}</td>
            <td><span v-for="a in f.agents" :key="a" class="chip agent">{{ a }}</span></td>
            <td>{{ f.repo_name || '全局' }}</td>
            <td class="num">{{ fmt(f.lines) }}</td>
            <td class="num"><b>{{ fmt(f.tokens_est) }}</b></td>
            <td>{{ shortDate(f.mtime) }}</td>
            <td>
              <span v-if="f.error" class="chip err">{{ f.error }}</span>
              <span v-if="f.stale" class="chip stale">疑似过时</span>
              <span v-if="!f.stale && !f.error" class="chip">正常</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- duplicates -->
    <div class="section-title">疑似重复规则 <span class="count">{{ dups.group_count }} 组 · 浪费 ≈{{ fmt(dups.wasted_tokens) }} tokens/会话</span></div>
    <div class="card">
      <div v-if="!dups.groups.length" class="empty">没有发现跨文件/跨仓库的重复规则块 🎉</div>
      <details v-for="(g, i) in dups.groups" :key="i" class="dup-group">
        <summary>
          <span class="chip dup">{{ g.cross_file ? '跨文件' : '文件内' }}</span>
          {{ g.members.length }} 处近似规则 · 浪费 ≈{{ fmt(g.wasted_tokens) }} tokens/会话
        </summary>
        <div v-for="m in g.members" :key="m.path + m.start_line" class="member">
          {{ m.path }} : {{ m.start_line }}-{{ m.end_line }} (≈{{ fmt(m.tokens_est) }} tokens)
        </div>
      </details>
    </div>

    <!-- stale -->
    <div class="section-title">疑似过时 <span class="count">{{ staleFiles.length }} 个文件</span></div>
    <div class="card">
      <div v-if="!staleFiles.length" class="empty">没有长期未更新且仓库仍活跃的规则文件 👍</div>
      <table v-else>
        <thead><tr><th>文件</th><th class="num">未动天数</th><th>最后修改</th><th>仓库最近活动</th></tr></thead>
        <tbody>
          <tr v-for="s in staleFiles" :key="s.path">
            <td class="path-cell" :title="s.path">{{ s.path }}</td>
            <td class="num" style="color: var(--orange);">{{ s.age_days }} 天</td>
            <td>{{ shortDate(s.mtime) }}</td>
            <td>{{ shortDate(s.repo_last_activity) || (s.repo ? '未知' : '全局文件') }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="note">
      token 为估算值（中文字符÷{{ report.settings_snapshot.cjk_ratio }} + 其他字符÷{{ report.settings_snapshot.other_ratio }}，误差 &lt;15%），
      用于决策参考而非计费；成本假设可在「设置」页调整。报告生成于 {{ report.generated_at }}。
    </div>
  </template>
</template>
