import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { 
  User, 
  Lock, 
  Bell, 
  Palette, 
  Shield, 
  ExternalLink,
  Save,
  Loader2,
  AlertCircle,
  Mail,
  Key,
  Cpu,
  Database
} from 'lucide-react'
import { toast } from 'sonner'
import { useAuth } from '../hooks/useAuth'
import { useModels } from '../hooks/useChatModels'
import { useProviderHealth } from '../hooks/useChatModels'
import { settingsAPI } from '../api/settings'

// Settings section component
const SettingsSection = ({ title, description, icon: Icon, children }) => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    className="glass-card p-6 mb-6"
  >
    <div className="flex items-start gap-4 mb-6">
      <div className="p-3 rounded-xl bg-white/5">
        <Icon className="w-5 h-5 text-blue-400" />
      </div>
      <div className="flex-1">
        <h3 className="text-lg font-semibold mb-1">{title}</h3>
        <p className="text-sm text-gray-400">{description}</p>
      </div>
    </div>
    {children}
  </motion.div>
)

// Form input component
const FormField = ({ label, children, error }) => (
  <div className="mb-4">
    <label className="block text-sm font-medium text-gray-300 mb-2">{label}</label>
    {children}
    {error && (
      <p className="mt-1 text-sm text-red-400">{error}</p>
    )}
  </div>
)

// Status badge
const StatusBadge = ({ status, text }) => {
  const colors = {
    online: 'bg-green-400/20 text-green-400',
    offline: 'bg-red-400/20 text-red-400',
    warning: 'bg-yellow-400/20 text-yellow-400',
  }
  
  return (
    <span className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-sm ${colors[status] || colors.offline}`}>
      <span className="w-2 h-2 rounded-full animate-pulse" />
      {text}
    </span>
  )
}

export const Settings = () => {
  const { user } = useAuth()
  const { data: models, isLoading: isLoadingModels } = useModels()
  const { data: health, isLoading: isLoadingHealth } = useProviderHealth()
  const { data: systemStatus, isLoading: isSystemLoading } = useQuery({
    queryKey: ['settings-system-status'],
    queryFn: settingsAPI.getSystemStatus,
    staleTime: 60 * 1000,
  })
  
  const [isSaving, setIsSaving] = useState(false)
  const [theme, setTheme] = useState('dark')

  const [profileForm, setProfileForm] = useState({
    fullName: user?.full_name || '',
    email: user?.email || '',
  })

  const [passwordForm, setPasswordForm] = useState({
    currentPassword: '',
    newPassword: '',
    confirmPassword: '',
  })

  const [ollamaForm, setOllamaForm] = useState({
    url: localStorage.getItem('ollama_url') || 'http://localhost:11434',
    apiKey: localStorage.getItem('ollama_api_key') || '',
    models: (localStorage.getItem('ollama_models') || 'gemma3:4b').split(','),
  })

  const [claudeForm, setClaudeForm] = useState({
    apiKey: localStorage.getItem('claude_api_key') || '',
  })

  useEffect(() => {
    setProfileForm({
      fullName: user?.full_name || '',
      email: user?.email || '',
    })
    setTheme(localStorage.getItem('theme') || 'dark')
  }, [user?.full_name, user?.email])

  const handleSaveProfile = async () => {
    try {
      setIsSaving(true)
      const updated = await settingsAPI.updateProfile(profileForm.fullName)
      setProfileForm((prev) => ({
        ...prev,
        fullName: updated.full_name || '',
      }))
      toast.success('Profile updated')
    } catch (error) {
      toast.error(error.response?.data?.message || 'Failed to update profile')
    } finally {
      setIsSaving(false)
    }
  }

  const handleChangePassword = async () => {
    if (!passwordForm.currentPassword || !passwordForm.newPassword || !passwordForm.confirmPassword) {
      toast.error('Fill out all password fields')
      return
    }
    if (passwordForm.newPassword !== passwordForm.confirmPassword) {
      toast.error('New password and confirmation must match')
      return
    }

    try {
      setIsSaving(true)
      await settingsAPI.changePassword(passwordForm.currentPassword, passwordForm.newPassword)
      setPasswordForm({
        currentPassword: '',
        newPassword: '',
        confirmPassword: '',
      })
      toast.success('Password changed')
    } catch (error) {
      toast.error(error.response?.data?.message || 'Failed to change password')
    } finally {
      setIsSaving(false)
    }
  }

  const handleSaveOllama = () => {
    if (!ollamaForm.url) {
      toast.error('Ollama URL is required')
      return
    }
    localStorage.setItem('ollama_url', ollamaForm.url)
    localStorage.setItem('ollama_api_key', ollamaForm.apiKey)
    localStorage.setItem('ollama_models', ollamaForm.models.join(','))
    toast.success('Ollama settings saved')
  }

  const handleSaveClaude = () => {
    if (!claudeForm.apiKey) {
      toast.error('Claude API key is required')
      return
    }
    localStorage.setItem('claude_api_key', claudeForm.apiKey)
    toast.success('Claude API key saved')
  }

  return (
    <div className="p-8">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="max-w-4xl mx-auto"
      >
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-display font-bold text-gradient mb-2">
            Settings
          </h1>
          <p className="text-gray-400">
            Manage your account, preferences, and API connections
          </p>
        </div>

        {/* Profile Section */}
        <SettingsSection
          title="Profile"
          description="Update your personal information"
          icon={User}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <FormField label="Full Name">
              <input
                type="text"
                value={profileForm.fullName}
                onChange={(e) => setProfileForm({ ...profileForm, fullName: e.target.value })}
                className="glass-input w-full"
                placeholder="Your full name"
              />
            </FormField>
            
            <FormField label="Email Address">
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                <input
                  type="email"
                  value={profileForm.email}
                  disabled
                  className="glass-input w-full pl-10 opacity-50 cursor-not-allowed"
                />
              </div>
              <p className="mt-1 text-xs text-gray-500">Email cannot be changed</p>
            </FormField>
          </div>
          
          <div className="flex items-center gap-4 mt-6">
            <button
              onClick={handleSaveProfile}
              disabled={isSaving}
              className="glass-button-primary px-6 py-2 flex items-center gap-2"
            >
              {isSaving ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  Save Changes
                </>
              )}
            </button>
          </div>
        </SettingsSection>

        {/* Security Section */}
        <SettingsSection
          title="Security"
          description="Manage your password and security settings"
          icon={Lock}
        >
          <div className="space-y-4">
            <FormField label="Current Password">
              <div className="relative">
                <Key className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                <input
                  type="password"
                  value={passwordForm.currentPassword}
                  onChange={(e) => setPasswordForm({ ...passwordForm, currentPassword: e.target.value })}
                  className="glass-input w-full pl-10"
                  placeholder="********"
                />
              </div>
            </FormField>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <FormField label="New Password">
                <input
                  type="password"
                  value={passwordForm.newPassword}
                  onChange={(e) => setPasswordForm({ ...passwordForm, newPassword: e.target.value })}
                  className="glass-input w-full"
                  placeholder="********"
                />
              </FormField>
              
              <FormField label="Confirm New Password">
                <input
                  type="password"
                  value={passwordForm.confirmPassword}
                  onChange={(e) => setPasswordForm({ ...passwordForm, confirmPassword: e.target.value })}
                  className="glass-input w-full"
                  placeholder="********"
                />
              </FormField>
            </div>
          </div>
          
          <div className="flex items-center gap-4 mt-6">
            <button
              type="button"
              onClick={handleChangePassword}
              className="glass-button-primary px-6 py-2"
            >
              Change Password
            </button>
          </div>
        </SettingsSection>

        {/* AI Providers Section */}
        <SettingsSection
          title="AI Providers"
          description="Configure your AI model connections and preferences"
          icon={Cpu}
        >
          <div className="space-y-4">
            {/* Ollama Status */}
            <div className="p-4 rounded-lg bg-white/5">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  <Database className="w-5 h-5 text-blue-400" />
                  <div>
                    <p className="font-medium">Ollama (Local Models)</p>
                    <p className="text-sm text-gray-400">Run AI models locally on your machine</p>
                  </div>
                </div>
                {isLoadingHealth ? (
                  <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
                ) : (health?.ollama?.healthy ?? health?.ollama?.ok) ? (
                  <StatusBadge status="online" text="Connected" />
                ) : (
                  <StatusBadge status="offline" text="Disconnected" />
                )}
              </div>

              {/* Ollama Configuration Fields */}
              <div className="space-y-4 mb-4 p-3 rounded-lg bg-white/5">
                <FormField label="Ollama API URL">
                  <input
                    type="text"
                    value={ollamaForm.url}
                    onChange={(e) => setOllamaForm({ ...ollamaForm, url: e.target.value })}
                    className="glass-input w-full"
                    placeholder="http://localhost:11434"
                  />
                </FormField>

                <FormField label="API Key (Optional)">
                  <div className="relative">
                    <Key className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                    <input
                      type="password"
                      value={ollamaForm.apiKey}
                      onChange={(e) => setOllamaForm({ ...ollamaForm, apiKey: e.target.value })}
                      className="glass-input w-full pl-10"
                      placeholder="Your Ollama API key (if required)"
                    />
                  </div>
                </FormField>

                <FormField label="Default Models (comma-separated)">
                  <input
                    type="text"
                    value={ollamaForm.models.join(', ')}
                    onChange={(e) => setOllamaForm({
                      ...ollamaForm,
                      models: e.target.value.split(',').map(m => m.trim()).filter(Boolean)
                    })}
                    className="glass-input w-full"
                    placeholder="gemma3:4b, kimi-k2.5:cloud"
                  />
                </FormField>

                <button
                  onClick={handleSaveOllama}
                  className="glass-button-primary px-4 py-2 flex items-center gap-2 w-full justify-center"
                >
                  <Save className="w-4 h-4" />
                  Save Ollama Settings
                </button>
              </div>

              {!isLoadingHealth && !(health?.ollama?.healthy ?? health?.ollama?.ok) && (
                <div className="p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-yellow-400 text-sm flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="font-medium mb-1">Ollama not detected</p>
                    <p>Make sure Ollama is running at the URL above</p>
                    <a
                      href="https://ollama.com"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 mt-2 text-blue-400 hover:text-blue-300"
                    >
                      Download Ollama <ExternalLink className="w-3 h-3" />
                    </a>
                  </div>
                </div>
              )}

              {isLoadingModels ? (
                <div className="flex items-center gap-2 text-sm text-gray-400 mt-3">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Loading available models...
                </div>
              ) : models?.ollama?.length > 0 ? (
                <div className="mt-3">
                  <p className="text-sm text-gray-400 mb-2">Available models:</p>
                  <div className="flex flex-wrap gap-2">
                    {models.ollama.map((model) => (
                      <span
                        key={model.id}
                        className="px-3 py-1 rounded-full bg-white/10 text-sm"
                      >
                        {model.name || model.id}
                      </span>
                    ))}
                  </div>
                </div>
              ) : !isLoadingModels && (health?.ollama?.healthy ?? health?.ollama?.ok) ? (
                <p className="text-sm text-gray-400 mt-3">
                  Ollama is reachable, but no models were returned by `/api/tags`.
                </p>
              ) : null}

              <p className="mt-3 text-xs text-gray-500">
                This app reads models directly from your Ollama instance. If you use Ollama Cloud through the Ollama app,
                cloud models should appear here automatically once they show up in Ollama `/api/tags`.
              </p>
            </div>

            {/* Claude API Section */}
            <div className="p-4 rounded-lg bg-white/5">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className="w-5 h-5 rounded bg-orange-500 flex items-center justify-center text-xs font-bold">
                    C
                  </div>
                  <div>
                    <p className="font-medium">Claude API (Optional)</p>
                    <p className="text-sm text-gray-400">Use Anthropic&apos;s Claude for cloud-based AI</p>
                  </div>
                </div>
                {isLoadingHealth ? (
                  <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
                ) : (health?.anthropic?.healthy ?? health?.anthropic?.ok) ? (
                  <StatusBadge status="online" text="Connected" />
                ) : (
                  <StatusBadge status="warning" text="Not Configured" />
                )}
              </div>

              <div className="space-y-4 p-3 rounded-lg bg-white/5">
                <FormField label="API Key">
                  <div className="relative">
                    <Key className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                    <input
                      type="password"
                      value={claudeForm.apiKey}
                      onChange={(e) => setClaudeForm({ ...claudeForm, apiKey: e.target.value })}
                      placeholder="sk-ant-..."
                      className="glass-input w-full pl-10"
                    />
                  </div>
                  <p className="mt-1 text-xs text-gray-500">
                    Your API key is stored securely in your browser.
                    <a
                      href="https://console.anthropic.com"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-400 hover:text-blue-300 inline-flex items-center gap-1"
                    >
                      Get API key <ExternalLink className="w-3 h-3" />
                    </a>
                  </p>
                </FormField>

                <button
                  onClick={handleSaveClaude}
                  className="glass-button-primary px-4 py-2 flex items-center gap-2 w-full justify-center"
                >
                  <Save className="w-4 h-4" />
                  Save Claude API Key
                </button>
              </div>
            </div>
          </div>
        </SettingsSection>

        {/* Notifications Section */}
        <SettingsSection
          title="Notifications"
          description="Configure your notification preferences"
          icon={Bell}
        >
          <div className="space-y-3">
            {[
              { id: 'document-processing', label: 'Document processing complete', default: true },
              { id: 'new-features', label: 'New features and updates', default: true },
              { id: 'security', label: 'Security alerts', default: true, disabled: true },
            ].map((setting) => (
              <div key={setting.id} className="flex items-center justify-between p-3 rounded-lg bg-white/5">
                <span className={setting.disabled ? 'text-gray-500' : ''}>
                  {setting.label}
                  {setting.disabled && <span className="text-xs text-gray-500 ml-2">(Required)</span>}
                </span>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    defaultChecked={setting.default}
                    disabled={setting.disabled}
                    className="sr-only peer"
                  />
                  <div className={`
                    w-11 h-6 bg-white/10 peer-focus:outline-none rounded-full peer 
                    peer-checked:after:translate-x-full peer-checked:after:border-white 
                    after:content-[''] after:absolute after:top-[2px] after:left-[2px] 
                    after:bg-white after:border-gray-300 after:border after:rounded-full 
                    after:h-5 after:w-5 after:transition-all
                    peer-checked:bg-blue-500
                    ${setting.disabled ? 'opacity-50 cursor-not-allowed' : ''}
                  `}></div>
                </label>
              </div>
            ))}
          </div>
        </SettingsSection>

        {/* Appearance Section */}
        <SettingsSection
          title="Appearance"
          description="Customize the look and feel of the application"
          icon={Palette}
        >
          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 rounded-lg bg-white/5">
              <span>Theme</span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => {
                    setTheme('dark')
                    localStorage.setItem('theme', 'dark')
                    toast.success('Theme set to Dark')
                  }}
                  className={`px-4 py-2 rounded-lg text-sm transition-colors ${
                    theme === 'dark'
                      ? 'bg-blue-500 text-white'
                      : 'bg-white/10 text-gray-400 hover:bg-white/20'
                  }`}
                >
                  Dark
                </button>
                <button
                  onClick={() => {
                    setTheme('light')
                    localStorage.setItem('theme', 'light')
                    toast.success('Theme set to Light')
                  }}
                  className={`px-4 py-2 rounded-lg text-sm transition-colors ${
                    theme === 'light'
                      ? 'bg-blue-500 text-white'
                      : 'bg-white/10 text-gray-400 hover:bg-white/20'
                  }`}
                >
                  Light
                </button>
                <button
                  onClick={() => {
                    setTheme('system')
                    localStorage.setItem('theme', 'system')
                    toast.success('Theme set to System')
                  }}
                  className={`px-4 py-2 rounded-lg text-sm transition-colors ${
                    theme === 'system'
                      ? 'bg-blue-500 text-white'
                      : 'bg-white/10 text-gray-400 hover:bg-white/20'
                  }`}
                >
                  System
                </button>
              </div>
            </div>
            <div className="flex items-center justify-between p-3 rounded-lg bg-white/5">
              <span>Backend Connectivity</span>
              {isSystemLoading ? (
                <span className="text-sm text-gray-400">Checking...</span>
              ) : systemStatus?.status === 'ok' ? (
                <span className="text-sm text-green-400">API reachable</span>
              ) : (
                <span className="text-sm text-red-400">API unavailable</span>
              )}
            </div>
          </div>
        </SettingsSection>

        {/* Privacy & Security */}
        <SettingsSection
          title="Privacy & Security"
          description="Manage your privacy settings and data"
          icon={Shield}
        >
          <div className="p-4 rounded-lg bg-white/5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <p className="font-medium">Data Export</p>
                <p className="text-sm text-gray-400">Download all your data including documents and conversations</p>
              </div>
              <button className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-sm transition-colors">
                Export Data
              </button>
            </div>

            <div className="border-t border-white/10 pt-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-red-400">Delete Account</p>
                  <p className="text-sm text-gray-400">Permanently delete your account and all associated data</p>
                </div>
                <button className="px-4 py-2 rounded-lg bg-red-500/20 hover:bg-red-500/30 text-red-400 text-sm transition-colors">
                  Delete Account
                </button>
              </div>
            </div>
          </div>
        </SettingsSection>

        {/* Role info */}
        {user?.role && (
          <div className="text-center text-sm text-gray-500 mt-8">
            Your account role: <span className="text-gray-300 capitalize">{user.role}</span>
          </div>
        )}
      </motion.div>
    </div>
  )
}
