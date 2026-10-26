<script setup>
import { onMounted, onUnmounted, ref, computed } from 'vue'
import { api } from '../api'

const AGENT_LABELS = { 'zcode': 'ZCode', 'claude-code': 'Claude Code', 'codex': 'Codex' }
const PAGE = 50

const filters = ref({ agents: [], projects: [] })
const agent = ref('')
const project = ref('')
const keyword = ref('')
const searching = ref(false)
const list = ref({ total: 0, items: [], offset: 0 })
const hits = ref([])           // message-level hits for the keyword
const detail = ref(null)
const detailId = ref(null)
const indexing = ref(false)
const indexStatus = ref(null)
const error = ref('')
const maskExport = ref(false)
let timer = null

const fmtTime = (ts) => {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
const agentLabel = (a) => AGENT_LABELS[a] || a

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/** Escape then wrap keyword occurrences in <mark>; server-side 【】 markers too. */
function highlight(text, kw) {
  let html = escapeHtml(text || '')
  if (kw) {
    const esc = escapeHtml(kw).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    html = html.replace(new RegExp(esc, 'gi'), m => `<mark>${m}</mark>`)
  }
  return html
}

function highlightSnippet(snippet) {
  // server marks hits with 【kw】; convert to <mark>, keyword itself highlighted
  return highlight((snippet || '').replace(/【|】/g, ''), keyword.value.trim())
}

const canLoadMore = computed(() =>
  list.value.items.length < list.value.total)

async function loadFilters() {
  try { filters.value = await api.sessionFilters() } catch { /* ignore */ }
}

async function loadList(append = false) {
  searching.value = true
  try {
    const params = { limit: PAGE, offset: append ? list.value.items.length : 0 }
    if (agent.value) params.agent = agent.value
    if (project.value) params.project = project.value
    const kw = keyword.value.trim()
    if (kw) params.q = kw
    const res = await api.listSessions(params)
    list.value = {
      ...res,
      items: append ? [...list.value.items, ...res.items] : res.items,
    }
    // message-level hits alongside session hits
    hits.value = kw ? (await api.searchMessages(kw, agent.value, 12)).items : []
  } catch (e) {
    error.value = e.message
  } finally {
    searching.value = false
  }
}

async function openSession(id) {
  detailId.value = id
  detail.value = null
  try {
    detail.value = await api.sessionDetail(id)
  } catch (e) {
    error.value = e.message
  }
}

async function startIndex() {
  error.value = ''
  try {
    await api.indexSessions(false)
    indexing.value = true
    timer = setInterval(async () => {
      try {
        const st = await api.sessionIndexStatus()
        indexStatus.value = st
        if (!st.running) {
          clearInterval(timer)
          indexing.value = false
          if (st.error) error.value = st.error
          await Promise.all([loadFilters(), loadList()])
        }
      } catch (e) {
        clearInterval(timer)
        indexing.value = false
        error.value = e.message
      }
    }, 800)
  } catch (e) {
    error.value = e.message
  }
}

function messageBlocks(content) {
  const lines = (content || '').split('\n')
  const text = lines.filter(l => !l.startsWith('[tool')).join('\n').trim()
  const tools = lines.filter(l => l.startsWith('[tool'))
  return { text, tools }
}

onMounted(async () => {
  await Promise.all([loadFilters(), loadList()])
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <div class="card" style="padding: 12px 14px;">
    <div class="sessions-toolbar">
      <div class="agent-chips">
        <button class="tab" :class="{ active: agent === '' }" @click="agent = ''; loadList()">全部</button>
        <button
          v-for="a in filters.agents" :key="a.id"
          class="tab" :class="{ active: agent === a.id }"
          @click="agent = a.id; loadList()"
        >{{ agentLabel(a.id) }} ({{ a.count }})</button>
      </div>
      <select v-model="project" class="project-select" @change="loadList()">
        <option value="">全部项目</option>
        <option v-for="p in filters.projects" :key="p" :value="p">{{ p }}</option>
      </select>
      <input
        v-model="keyword" type="text" class="search-input"
        placeholder="全文搜索：nginx、报错信息、任何关键词…"
        @keyup.enter="loadList()"
      />
      <button :disabled="searching" @click="loadList()">{{ searching ? '搜索中…' : '搜索' }}</button>
      <button class="primary" :disabled="indexing" @click="startIndex">
        {{ indexing ? '索引中…' : '索引会话' }}
      </button>
    </div>
    <div v-if="indexing && indexStatus" class="progress-msg">
      {{ indexStatus.phase }} · {{ indexStatus.done }}/{{ indexStatus.total }} · {{ indexStatus.message }}
    </div>
    <div v-if="error" style="color: var(--red); margin-top: 8px;">{{ error }}</div>
  </div>

  <div v-if="!list.items.length" class="card empty">
    {{ list.total === 0 && keyword ? '没有匹配的会话 —— 换个关键词试试' : '还没有会话数据 —— 点「索引会话」解析本机 ZCode / Claude Code / Codex 的历史记录' }}
  </div>

  <div v-if="list.items.length" class="sessions-layout">
    <!-- session list -->
    <div class="card session-list">
      <div class="hint" style="padding: 2px 4px 8px;">
        {{ keyword ? `「${keyword}」命中 ${list.total} 个会话` : `${list.total} 个会话（按开始时间倒序）` }}
      </div>
      <div
        v-for="s in list.items" :key="s.id"
        class="session-item" :class="{ selected: s.id === detailId }"
        @click="openSession(s.id)"
      >
        <div class="session-item-head">
          <span class="agent-dot" :class="s.agent"></span>
          <span class="agent-name">{{ agentLabel(s.agent) }}</span>
          <span class="project-name">{{ s.project || '—' }}</span>
          <span class="session-date">{{ fmtTime(s.started_at) }}</span>
        </div>
        <div class="session-title">{{ s.title || '(无标题)' }}</div>
        <div v-if="s.snippet" class="session-snippet" v-html="highlightSnippet(s.snippet)"></div>
        <div class="session-meta">{{ s.msg_count }} 条消息<template v-if="s.hit_count"> · {{ s.hit_count }} 处命中</template></div>
      </div>
      <div v-if="canLoadMore" style="text-align: center; padding: 6px;">
        <button :disabled="searching" @click="loadList(true)">加载更多（{{ list.total - list.items.length }}）</button>
      </div>

      <!-- message-level hits -->
      <template v-if="hits.length">
        <div class="section-title" style="margin: 12px 0 8px;">消息级命中 <span class="count">Top {{ hits.length }}</span></div>
        <div
          v-for="h in hits" :key="'h' + h.id"
          class="session-item msg-hit" @click="openSession(h.session_id)"
        >
          <div class="session-item-head">
            <span class="agent-dot" :class="h.agent"></span>
            <span class="agent-name">{{ agentLabel(h.agent) }}</span>
            <span class="project-name">{{ h.project }}</span>
            <span class="session-date">{{ fmtTime(h.ts) }}</span>
          </div>
          <div class="session-snippet" v-html="highlight(h.snippet, keyword)"></div>
          <div class="session-meta">{{ h.role }} · {{ (h.title || '').slice(0, 40) }}</div>
        </div>
      </template>
    </div>

    <!-- detail pane -->
    <div class="card session-detail">
      <div v-if="!detail" class="empty">← 点击左侧会话查看完整对话</div>
      <template v-else>
        <div class="detail-head">
          <div>
            <div class="detail-title">{{ detail.title || '(无标题)' }}</div>
            <div class="hint">
              {{ agentLabel(detail.agent) }} · {{ detail.project }}
              <template v-if="detail.project_path">（{{ detail.project_path }}）</template>
              · {{ fmtTime(detail.started_at) }} → {{ fmtTime(detail.ended_at) }}
              · {{ detail.msg_count }} 条消息
            </div>
            <label class="hint" style="display: inline-flex; align-items: center; gap: 5px; margin-top: 6px;">
              <input v-model="maskExport" type="checkbox" /> 导出时打码敏感信息
            </label>
          </div>
          <a :href="api.exportUrl(detail.id, maskExport)" download>
            <button>导出 Markdown</button>
          </a>
        </div>
        <div class="messages">
          <div v-for="(m, i) in detail.messages" :key="i" class="msg" :class="m.role">
            <div class="msg-role">
              <span v-if="m.role === 'user'">👤 user</span>
              <span v-else-if="m.role === 'assistant'">🤖 assistant</span>
              <span v-else>🔧 {{ m.tool_name || 'tool' }}</span>
              <span class="msg-time">{{ fmtTime(m.ts) }}</span>
            </div>
            <div class="msg-text" v-html="highlight(messageBlocks(m.content).text, keyword)"></div>
            <div v-if="messageBlocks(m.content).tools.length" class="msg-tools">
              <div v-for="t in messageBlocks(m.content).tools" :key="t">{{ t }}</div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.sessions-toolbar {
  display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
}
.agent-chips { display: flex; gap: 4px; flex-wrap: wrap; }
.project-select, .search-input {
  background: var(--bg); border: 1px solid var(--border); color: var(--text);
  border-radius: 8px; padding: 6px 10px; font-size: 13px; outline: none;
}
.search-input { flex: 1; min-width: 220px; }

.sessions-layout {
  display: grid; grid-template-columns: minmax(320px, 5fr) minmax(380px, 7fr);
  gap: 16px; align-items: start;
}
.session-list { max-height: calc(100vh - 240px); overflow-y: auto; padding: 10px; }
.session-item {
  border: 1px solid var(--border); border-radius: 8px;
  padding: 9px 11px; margin-bottom: 8px; cursor: pointer;
  background: var(--panel-2);
}
.session-item:hover { border-color: var(--blue); }
.session-item.selected { border-color: var(--green); }
.msg-hit { padding: 7px 11px; }
.session-item-head { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.agent-dot {
  width: 9px; height: 9px; border-radius: 50%;
  background: var(--muted); display: inline-block; flex: none;
}
.agent-dot.zcode { background: var(--green); }
.agent-dot.claude-code { background: var(--blue); }
.agent-dot.codex { background: var(--orange); }
.agent-name { color: var(--text); font-weight: 600; }
.project-name { color: var(--purple); }
.session-date { color: var(--muted); margin-left: auto; }
.session-title {
  margin-top: 4px; font-size: 13px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.session-snippet { margin-top: 4px; font-size: 12px; color: var(--muted); }
.session-snippet :deep(mark), .msg-text :deep(mark) {
  color: var(--orange); background: rgba(210, 153, 34, 0.15); font-weight: 700;
}
.session-meta { margin-top: 4px; font-size: 11px; color: var(--muted); }

.session-detail { padding: 14px 16px; max-height: calc(100vh - 240px); display: flex; flex-direction: column; }
.detail-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; padding-bottom: 10px; border-bottom: 1px solid var(--border); }
.detail-title { font-weight: 700; font-size: 14px; margin-bottom: 2px; }
.messages { overflow-y: auto; padding-top: 10px; }
.msg { margin-bottom: 12px; }
.msg-role { font-size: 12px; color: var(--muted); margin-bottom: 3px; display: flex; gap: 8px; }
.msg-time { font-size: 11px; }
.msg.user .msg-text {
  background: rgba(88, 166, 255, 0.08);
  border-left: 3px solid var(--blue);
}
.msg.assistant .msg-text {
  background: var(--panel-2);
  border-left: 3px solid var(--green);
}
.msg-text {
  border-radius: 6px; padding: 8px 10px; font-size: 13px;
  white-space: pre-wrap; word-break: break-word;
}
.msg-tools {
  font-family: ui-monospace, Consolas, monospace; font-size: 11px;
  color: var(--purple); padding: 4px 10px;
}
</style>
