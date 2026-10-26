<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const AGENT_LABELS = { 'zcode': 'ZCode', 'claude-code': 'Claude Code', 'codex': 'Codex' }
const AGENT_COLORS = { 'zcode': 'var(--green)', 'claude-code': 'var(--blue)', 'codex': 'var(--orange)' }

const stats = ref(null)
const error = ref('')
const hover = ref(null)

const agentLabel = (a) => AGENT_LABELS[a] || a
const agentColor = (a) => AGENT_COLORS[a] || 'var(--purple)'
const fmt = (n) => (n ?? 0).toLocaleString('zh-CN')
const fmtDate = (ts) => ts ? new Date(ts * 1000).toLocaleDateString('zh-CN') : '—'

const maxMonth = () => {
  if (!stats.value) return 1
  return Math.max(1, ...stats.value.by_month.map(m => m.sessions))
}

function stackSegments(month) {
  const agents = Object.keys(month.by_agent)
  const total = month.sessions || 1
  let acc = 0
  return agents.map(a => {
    const seg = { agent: a, count: month.by_agent[a], offset: acc }
    acc += month.by_agent[a]
    return seg
  }).map(seg => ({
    ...seg,
    heightPct: (seg.count / Math.max(month.sessions, maxMonth())) * 100,
  }))
}

onMounted(async () => {
  try { stats.value = await api.sessionStats() } catch (e) { error.value = e.message }
})
</script>

<template>
  <div v-if="error" class="card" style="color: var(--red);">{{ error }}</div>

  <div v-if="!stats" class="card empty">加载中…</div>

  <template v-if="stats">
    <div v-if="!stats.totals.sessions" class="card empty">
      还没有会话数据 —— 去「会话档案馆」点「索引会话」。
    </div>

    <template v-if="stats.totals.sessions">
      <div class="stat-grid">
        <div class="stat">
          <div class="label">总会话</div>
          <div class="value">{{ fmt(stats.totals.sessions) }}</div>
          <div class="foot" v-if="stats.totals.first">
            {{ fmtDate(stats.totals.first) }} → {{ fmtDate(stats.totals.last) }}
          </div>
        </div>
        <div class="stat">
          <div class="label">消息总数</div>
          <div class="value">{{ fmt(stats.totals.messages) }}</div>
        </div>
        <div class="stat">
          <div class="label">使用过的 Agent</div>
          <div class="value">{{ fmt(stats.totals.agents) }}</div>
          <div class="foot">覆盖 {{ fmt(stats.totals.projects) }} 个项目</div>
        </div>
      </div>

      <!-- monthly stacked bar chart (pure SVG) -->
      <div class="section-title">近 12 个月会话活跃度</div>
      <div class="card">
        <div class="chart">
          <div v-for="m in stats.by_month" :key="m.month" class="chart-col"
               @mouseenter="hover = m" @mouseleave="hover = null">
            <div class="chart-bar">
              <div
                v-for="seg in stackSegments(m)"
                :key="seg.agent"
                class="chart-seg"
                :style="{
                  height: seg.heightPct + '%',
                  background: agentColor(seg.agent),
                  order: stackSegments(m).length - stackSegments(m).indexOf(seg),
                }"
              ></div>
            </div>
            <div class="chart-label">{{ m.month.slice(2) }}</div>
            <div v-if="hover && hover.month === m.month" class="chart-tip">
              <b>{{ m.month }}</b> · {{ m.sessions }} 会话
              <div v-for="(c, a) in m.by_agent" :key="a">
                {{ agentLabel(a) }}: {{ c }}
              </div>
            </div>
          </div>
        </div>
        <div class="chart-legend">
          <span v-for="a in stats.by_agent" :key="a.agent" class="legend-item">
            <span class="legend-dot" :style="{ background: agentColor(a.agent) }"></span>
            {{ agentLabel(a.agent) }}
          </span>
        </div>
      </div>

      <!-- per agent table -->
      <div class="section-title">按 Agent</div>
      <div class="card" style="padding: 6px 12px;">
        <table>
          <thead>
            <tr><th>Agent</th><th class="num">会话</th><th class="num">消息</th><th class="num">平均会话长度</th></tr>
          </thead>
          <tbody>
            <tr v-for="a in stats.by_agent" :key="a.agent">
              <td><span class="legend-dot" :style="{ background: agentColor(a.agent) }"></span> {{ agentLabel(a.agent) }}</td>
              <td class="num">{{ fmt(a.sessions) }}</td>
              <td class="num">{{ fmt(a.messages) }}</td>
              <td class="num">{{ a.avg_messages }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- top projects -->
      <div class="section-title">最活跃项目 <span class="count">Top {{ stats.top_projects.length }}</span></div>
      <div class="card" style="padding: 6px 12px;">
        <table>
          <thead><tr><th>项目</th><th class="num">会话</th><th class="num">消息</th></tr></thead>
          <tbody>
            <tr v-for="p in stats.top_projects" :key="p.project">
              <td>{{ p.project }}</td>
              <td class="num">{{ fmt(p.sessions) }}</td>
              <td class="num">{{ fmt(p.messages) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="note">统计基于本地索引数据；索引更新后刷新本页即可。</div>
    </template>
  </template>
</template>

<style scoped>
.chart {
  display: flex; align-items: flex-end; gap: 8px;
  height: 180px; padding: 10px 6px 0;
}
.chart-col {
  flex: 1; display: flex; flex-direction: column; align-items: center;
  height: 100%; position: relative;
}
.chart-bar {
  flex: 1; width: 70%; max-width: 46px;
  display: flex; flex-direction: column; justify-content: flex-end;
  border-radius: 6px 6px 0 0; overflow: hidden;
  background: var(--panel-2); position: relative;
}
.chart-seg { width: 100%; min-height: 1px; }
.chart-label { margin-top: 6px; font-size: 11px; color: var(--muted); }
.chart-tip {
  position: absolute; bottom: 100%; left: 50%; transform: translateX(-50%);
  background: var(--panel-2); border: 1px solid var(--border);
  border-radius: 8px; padding: 6px 10px; font-size: 12px;
  white-space: nowrap; z-index: 5; margin-bottom: 4px;
}
.chart-legend { display: flex; gap: 16px; margin-top: 10px; flex-wrap: wrap; }
.legend-item { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--muted); }
.legend-dot {
  width: 9px; height: 9px; border-radius: 50%; display: inline-block; flex: none;
}
</style>
