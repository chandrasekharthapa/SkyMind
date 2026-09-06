# SkyMind Copilot — Configuration Reference

## 1. Environment Variables

| Variable | Scope | Default Value | Description |
| :--- | :--- | :--- | :--- |
| `SERPAPI_API_KEY` | Backend | Mock Fallback | API key for Google Flights search via SerpAPI |
| `OPENAI_API_KEY` | Backend | Optional | API key for OpenAI LLM copilot capabilities |
| `LANGCHAIN_API_KEY` | Backend | Optional | LangSmith tracing and evaluation API key |
| `NEXT_PUBLIC_API_URL` | Frontend | `http://127.0.0.1:8000` | FastAPI backend base URL |
| `ENV` | Global | `development` | Environment mode (`development` / `production`) |

---

## 2. Configuration Files

- **`frontend/.env.local`**: Local environment overrides for Next.js frontend.
- **`frontend/tsconfig.json`**: TypeScript configuration (`strict: false`, `strictNullChecks: true`, path alias `@/* -> ./*`).
- **`backend/evals/`**: Evaluation suite thresholds and benchmark rules.
