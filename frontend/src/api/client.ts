// All communication with the backend goes through these functions.
import axios, { AxiosError } from 'axios'
import type {
  DestinationDetail,
  DestinationSummary,
  KnowledgeOverview,
  PlanRequest,
  PlanResult,
  QueryResult,
  SavedDetail,
  SavedSummary,
} from './types'

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '')

const http = axios.create({ baseURL: `${API_BASE_URL}/api`, timeout: 20000 })

/** Turn any request failure into one readable sentence for the UI. */
export function errorMessage(error: unknown): string {
  if (error instanceof AxiosError) {
    if (!error.response) {
      return `Could not reach the planner API at ${API_BASE_URL}. Start the backend (uvicorn app.main:app) and try again.`
    }
    const detail = error.response.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail[0]?.msg) {
      const field = detail[0].loc?.slice(1).join('.')
      return field ? `${field}: ${detail[0].msg}` : detail[0].msg
    }
    return `The API answered with status ${error.response.status}.`
  }
  return 'Something unexpected went wrong.'
}

export const api = {
  destinations: () => http.get<DestinationSummary[]>('/destinations').then((r) => r.data),
  destination: (id: string) => http.get<DestinationDetail>(`/destinations/${id}`).then((r) => r.data),
  plan: (request: PlanRequest) => http.post<PlanResult>('/plan', request).then((r) => r.data),
  knowledge: (id: string) => http.get<KnowledgeOverview>(`/knowledge/${id}`).then((r) => r.data),
  query: (destination_id: string, query: string) =>
    http.post<QueryResult>('/knowledge/query', { destination_id, query }).then((r) => r.data),
  saved: () => http.get<SavedSummary[]>('/itineraries').then((r) => r.data),
  savedOne: (id: number) => http.get<SavedDetail>(`/itineraries/${id}`).then((r) => r.data),
  save: (title: string, request: PlanRequest) =>
    http.post<SavedDetail>('/itineraries', { title, request }).then((r) => r.data),
  remove: (id: number) => http.delete(`/itineraries/${id}`),
}
