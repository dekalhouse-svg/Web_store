/* WEB STORE — client API */
(() => {
  const API_BASE_URL = String(window.WEBSTORE_API_BASE_URL || 'http://127.0.0.1:8000/api').replace(/\/+$/, '');
  async function request(path, options = {}) {
    const normalized = path.startsWith('/') ? path : `/${path}`;
    const headers = new Headers(options.headers || {});
    if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
    const response = await fetch(`${API_BASE_URL}${normalized}`, {
      ...options, headers, credentials: 'omit',
    });
    if (response.status === 204) return null;
    const type = response.headers.get('content-type') || '';
    const data = type.includes('application/json') ? await response.json() : null;
    if (!response.ok) throw new Error(data?.detail || `Erreur API (${response.status})`);
    return data;
  }
  function visitorId() { return localStorage.getItem('webstore_visitor_id') || ''; }
  async function trackVisitor() {
    const id = visitorId();
    const data = await request('/visitors/track/', { method: 'POST', headers: id ? { 'X-Visitor-ID': id } : {} });
    if (data?.visitor_id) localStorage.setItem('webstore_visitor_id', data.visitor_id);
    return data;
  }
  const visitorHeaders = () => ({ 'X-Visitor-ID': visitorId() });
  window.WebStoreAPI = {
    request, trackVisitor,
    getCategories: () => request('/categories/'),
    getProjects: (params = {}) => request(`/projects/${new URLSearchParams(params).toString() ? `?${new URLSearchParams(params)}` : ''}`),
    getProject: slug => request(`/projects/${encodeURIComponent(slug)}/`),
    getAssetUrl: path => /^(https?:\/\/|data:)/i.test(path || '') ? path : `${API_BASE_URL}${String(path || '').startsWith('/') ? '' : '/'}${path || ''}`,
    getFavorite: slug => request(`/projects/${encodeURIComponent(slug)}/favorite/`, { headers: visitorHeaders() }),
    toggleFavorite: slug => request(`/projects/${encodeURIComponent(slug)}/favorite/`, { method: 'POST', headers: visitorHeaders() }),
    postComment: (slug, payload) => request(`/projects/${encodeURIComponent(slug)}/comments/`, { method: 'POST', headers: visitorHeaders(), body: JSON.stringify(payload) }),
    getComments: slug => request(`/projects/${encodeURIComponent(slug)}/comments/`),
    updateComment: (slug, id, token, payload) => request(`/projects/${encodeURIComponent(slug)}/comments/${id}/`, { method: 'PATCH', headers: { 'X-Comment-Token': token }, body: JSON.stringify(payload) }),
    deleteComment: (slug, id, token) => request(`/projects/${encodeURIComponent(slug)}/comments/${id}/`, { method: 'DELETE', headers: { ...visitorHeaders(), 'X-Comment-Token': token } }),
    reportComment: (slug, id, payload) => request(`/projects/${encodeURIComponent(slug)}/comments/${id}/reports/`, { method: 'POST', headers: visitorHeaders(), body: JSON.stringify(payload) }),
    postReport: (slug, payload) => request(`/projects/${encodeURIComponent(slug)}/reports/`, { method: 'POST', body: JSON.stringify(payload) }),
    getSimilarProjects: slug => request(`/projects/${encodeURIComponent(slug)}/similar/`),
    getDeveloper: id => request(`/developers/${id}/`),
    trackEvent: (slug, type) => request(`/projects/${encodeURIComponent(slug)}/events/`, { method: 'POST', body: JSON.stringify({ type }) }).catch(() => null),
  };
})();
