# Frontend Chat Integration Notes

This branch includes reusable chat integration helpers for backend chat ops:

- `src/lib/chatApi.js`
  - `fetchChatModels(token)` -> `GET /api/v1/chat/models`
  - `fetchProviderHealth(token)` -> `GET /api/v1/chat/providers/health`
  - `streamConversationMessage({...})` -> `POST /api/v1/chat/conversations/{id}/messages/stream`
- `src/hooks/useChatOps.js`
  - `useChatModels(token)`
  - `useProviderHealth(token)`

## API Base URL

Set `VITE_API_BASE_URL` to your backend API base (defaults to `http://localhost:8000/api/v1`).

Example:

```powershell
$env:VITE_API_BASE_URL="http://localhost:8000/api/v1"
```

## Streaming Event Contract

The stream parser supports:

- `event: delta` for token chunks
- `event: message` for persisted assistant metadata
- `event: done` for stream completion

