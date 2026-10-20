export type AnyRecord = Record<string, any>

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const demo = typeof window !== 'undefined' && localStorage.getItem('learnlens_bundled_demo') === '1'
  const demoPaths = ['/diagnosis', '/diagnostic/generate', '/diagnostic/evaluate', '/lesson/generate', '/quiz/generate', '/quiz/evaluate']
  const target = demo && demoPaths.includes(path.split('?')[0]) ? `${path}${path.includes('?') ? '&' : '?'}demo=true` : path
  const res = await fetch(`/api${target}`, { ...init, cache: 'no-store' })
  const text = await res.text()
  let data: any = null
  try { data = text ? JSON.parse(text) : null } catch { data = text }
  if (!res.ok) {
    const message = typeof data === 'string' ? data : data?.detail || data?.message || `Request failed (${res.status})`
    throw new Error(message)
  }
  return data as T
}

export function slugify(value: string) {
  return value.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 64) || 'topic'
}
