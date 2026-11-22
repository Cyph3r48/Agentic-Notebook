import apiClient from './client'

export const modelsAPI = {
  // Every provider's models for this user, with which are enabled, plus the default for new conversations.
  getSettings: async () => {
    const response = await apiClient.get('/settings/models')
    return response.data
  },

  // Saves the full state: { enabled_models: { provider: [ids] } | null, default: { provider, model } | null }.
  saveSettings: async ({ enabledModels, defaultModel }) => {
    const response = await apiClient.put('/settings/models', {
      enabled_models: enabledModels,
      default: defaultModel,
    })
    return response.data
  },
}
