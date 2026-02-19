import axios from 'axios'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1').replace(/\/+$/, '')

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
})

export function withAuth(headers = {}, token) {
  if (!token) return headers
  return {
    ...headers,
    Authorization: `Bearer ${token}`,
  }
}

