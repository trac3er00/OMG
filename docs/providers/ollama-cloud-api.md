# Ollama Cloud API

- Base URL: `https://ollama.com/api`
- Authentication: `Authorization: Bearer $OLLAMA_API_KEY`

## Endpoints

### List models

- `GET /tags`
- Full URL: `https://ollama.com/api/tags`
- Returns JSON with a `models` array.

### Chat

- `POST /chat`
- Full URL: `https://ollama.com/api/chat`
- Body fields:
  - `model` (string)
  - `messages` (array)
  - `stream` (boolean)
- Requires valid bearer token.
