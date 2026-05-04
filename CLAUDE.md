# whoismytd.ie — Project Context

## What This Is
A civic-tech website for Irish citizens to look up their TDs (Teachta Dála — Members of Parliament) and see their full voting record on Dáil legislation, with AI-generated plain-English bill summaries. Targeting the 34th Dáil (elected November 2024).

**Live URL:** whoismytd.ie (domain registered, not yet deployed)
**GitHub:** https://github.com/Brendanmccullen1/whoismytd

---

## Tech Stack

| Layer | Tech |
|---|---|
| Frontend | Plain HTML/CSS/JS — no framework, no build step |
| Backend | Python Flask (server.py) |
| Database | PostgreSQL 16 (Docker locally, cloud-ready via DATABASE_URL) |
| Data source | Oireachtas Open Data API — `https://api.oireachtas.ie/v1` |
| AI summaries | Anthropic Claude (`claude-haiku-4-5-20251001`) |
| Design system | Custom — dark/light mode, Irish green accents, Playfair Display + Inter |

---

## Running Locally

```bash
# 1. Start Postgres (requires Docker Desktop)
docker compose up -d

# 2. Activate venv and start Flask
source venv/bin/activate
python server.py          # → http://localhost:5000

# 3. (First time only) Populate the database
python populate.py
```

**Environment:** `.env` file (gitignored) at project root:
```
DATABASE_URL=postgresql://whoismytd:whoismytd@localhost:5432/whoismytd
ANTHROPIC_API_KEY=sk-...
```

---

## File Structure

```
whoismytd/
├── server.py              # Flask backend — all /api/* routes
├── populate.py            # One-time DB population from Oireachtas API
├── docker-compose.yml     # Postgres 16 local dev container
├── requirements.txt       # Flask, psycopg2-binary, anthropic, requests, python-dotenv
├── setup.sh               # One-command bootstrap (docker + populate)
├── .env                   # Secrets — gitignored
├── .gitignore
│
├── index.html             # Landing page (hero + live stats from /api/stats)
├── tds.html               # All TDs listing with search
├── td.html                # TD profile + voting record
├── bills.html             # Recent bills list
├── bill.html              # Bill detail + AI summary + vote breakdown
│
├── css/
│   └── main.css           # Full design system (tokens, components, layout)
│
└── js/
    ├── api.js             # fetchAPI() wrapper for all backend calls
    ├── main.js            # Theme toggle, goTo(), getQueryParam()
    ├── tds.js             # TD listing — search + constituency grouping
    ├── td.js              # TD profile — votes list, stats
    └── bill.js            # Bill detail — AI summary + breakdown bars
```

---

## Database Schema

6 tables in PostgreSQL:

```
constituencies   id, code, name
parties          id, code, name
members          id, pid (Oireachtas pId), full_name, first_name, last_name,
                 gender, constituency_id, party_id, date_start, date_end,
                 is_active, image_url
bills            id, bill_id, title, description, bill_type, bill_status,
                 date_introduced, uri
divisions        id, division_id, bill_id, title, date, ta_count, nil_count,
                 staon_count, result, uri
member_votes     id, member_id, division_id, vote ('Tá'|'Níl'|'Staon')
```

**Current data state:**
- ✓ 174 members (34th Dáil, elected 2024-11-29)
- ✓ 43 constituencies
- ✓ 11 parties
- ✗ Bills — empty (Oireachtas API returning 0 for bills endpoint)
- ✗ Divisions — empty (API pagination fails at skip=10000)
- ✗ Member votes — empty (depends on divisions)

---

## Backend API Routes

| Route | Source | Notes |
|---|---|---|
| `GET /api/tds` | DB | Members filtered to `date_start = '2024-11-29'` (34th Dáil) |
| `GET /api/td/<pid>` | DB | Member + their votes; pid = Oireachtas pId e.g. `MichaelMartin` |
| `GET /api/bills` | DB → API fallback | Falls back to live Oireachtas API if DB empty |
| `GET /api/bill/<bill_id>` | DB → API fallback | Same fallback pattern |
| `GET /api/summary/<bill_id>` | Claude AI | In-memory cache; uses DB bill text if available |
| `GET /api/division/<division_id>` | DB | Returns all member votes for a division |
| `GET /api/stats` | DB | Active TDs, constituencies, divisions, votes counts |

---

## Design System

- **Colours:** Dark slate surfaces (`#0B0D11` bg), Irish green accent (`#22C55E`)
- **Fonts:** Playfair Display (headings), Inter (body), JetBrains Mono (data)
- **Vote labels:** Always Irish — *Tá* (Yes) / *Níl* (No) / *Staon* (Abstain)
- **Default theme:** Dark. Toggle stored in `localStorage`
- **Design files:** `/Users/brendanmccullen/Downloads/Who is my td/` — full design system + UI kit prototypes

---

## Key Decisions Made

- **Plain HTML/CSS/JS** chosen over React/Angular for simplicity and zero build step
- **Flask** over Node because existing `api_query.py` was in Python
- **34th Dáil filter:** `date_start = '2024-11-29'` — the general election date. All prior members are in the DB but excluded from the UI
- **DATABASE_URL pattern** — single env var works locally (Docker) and on any cloud host (Railway/Render/Supabase) with zero code changes
- **Upsert pattern** throughout `populate.py` — safe to re-run at any time
- **API fallback** in `/api/bills` and `/api/bill` — bills/divisions DB is empty so these still hit the live API; once populated they'll switch to DB automatically

---

## What's Next / Known Issues

1. **Bills & divisions not populating** — Oireachtas `/v1/legislation` and `/v1/divisions` endpoints not returning data with current params. Need to investigate correct query params or scrape a different endpoint.
2. **Deploy to cloud** — Railway or Render recommended. Just set `DATABASE_URL` env var and push. No code changes needed.
3. **TD profile photos** — image URLs not in the current API response; could scrape from Oireachtas website.
4. **Constituency lookup by Eircode** — "Find your TD" flow should allow Eircode input, not just browsing.
5. **AI summary persistence** — summaries cached in memory only; restart loses them. Should persist to a `bill_summaries` table.
