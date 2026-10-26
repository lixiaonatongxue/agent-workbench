async function request(path, options = {}) {
  const resp = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`
    try {
      const body = await resp.json()
      if (body.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch { /* keep status text */ }
    throw new Error(detail)
  }
  return resp.json()
}

export const api = {
  health: () => request('/api/health'),
  agents: () => request('/api/agents'),
  startScan: (roots, includeGlobal) =>
    request('/api/scan', {
      method: 'POST',
      body: JSON.stringify({ roots, include_global: includeGlobal, wait: false }),
    }),
  scanStatus: () => request('/api/scan/status'),
  report: () => request('/api/doctor/report'),
  settings: () => request('/api/settings'),
  saveSettings: (settings) =>
    request('/api/settings', { method: 'PUT', body: JSON.stringify(settings) }),
  clearData: (scope = 'rules') => request(`/api/data?scope=${scope}`, { method: 'DELETE' }),

  indexSessions: (wait = false) =>
    request('/api/sessions/index', {
      method: 'POST',
      body: JSON.stringify({ wait }),
    }),
  sessionIndexStatus: () => request('/api/sessions/index/status'),
  listSessions: (params = {}) =>
    request('/api/sessions?' + new URLSearchParams(params).toString()),
  sessionFilters: () => request('/api/sessions/filters'),
  sessionStats: () => request('/api/sessions/stats'),
  sessionDetail: (id) => request(`/api/sessions/${id}`),
  searchMessages: (q, agent, limit = 20) => {
    const params = { q, limit }
    if (agent) params.agent = agent
    return request('/api/sessions/search?' + new URLSearchParams(params).toString())
  },
  exportUrl: (id, mask = false) => `/api/sessions/${id}/export?mask=${mask}`,
}
