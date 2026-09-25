const BASE = '/api'

async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`
    try {
      const body = await response.json()
      if (body.detail) {
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      }
    } catch {
      /* response had no JSON body */
    }
    throw new Error(detail)
  }
  return response.json()
}

export const getMeta = () => request('/meta')
export const getModes = () => request('/modes')
export const getBranches = () => request('/branches')
export const getColleges = (params = {}) => {
  const query = new URLSearchParams()
  if (params.recommendableOnly === false) query.set('recommendable_only', 'false')
  if (params.search) query.set('search', params.search)
  if (params.limit) query.set('limit', String(params.limit))
  const suffix = query.toString() ? `?${query}` : ''
  return request(`/colleges${suffix}`)
}

export const postRecommend = (payload) =>
  request('/recommend', { method: 'POST', body: JSON.stringify(payload) })
