# StudyBuddy — Frontend

Next.js 16 frontend for StudyBuddy. Communicates with the FastAPI backend over a REST + SSE API.

---

## Tech Stack

| Concern | Choice |
|---|---|
| Framework | Next.js 16 (App Router) |
| Language | TypeScript |
| Styling | Tailwind CSS v4 |
| State | Zustand |
| Forms | react-hook-form + zod |
| Auth | @react-oauth/google (Google Sign-In), custom redirect flow (LinkedIn) |
| HTTP | axios |

---

## Local Setup

### 1. Install dependencies

```bash
cd frontend
npm install
```

### 2. Configure environment variables

Create a `.env.local` file:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000

# Google OAuth — https://console.cloud.google.com → Credentials → OAuth 2.0 Client IDs
# Add http://localhost:3000 to Authorized JavaScript origins
NEXT_PUBLIC_GOOGLE_CLIENT_ID=<your-client-id>.apps.googleusercontent.com

# LinkedIn OAuth (optional — leave blank to hide the LinkedIn button)
# Add http://localhost:3000/auth/callback to Authorized redirect URLs in your LinkedIn app
NEXT_PUBLIC_LINKEDIN_CLIENT_ID=<your-linkedin-client-id>
NEXT_PUBLIC_LINKEDIN_REDIRECT_URI=http://localhost:3000/auth/callback
```

### 3. Start the development server

```bash
npm run dev
```

App is at `http://localhost:3000`.

> **Note:** Port 3000 is required — Google and LinkedIn OAuth are configured with this origin/redirect URI.

---

## Auth Flow

**Google** — The `GoogleLogin` component (from `@react-oauth/google`) opens Google's sign-in popup and returns an ID token. The frontend posts `{ credential: <id_token> }` to `POST /auth/google` on the backend.

**LinkedIn** — Clicking "Continue with LinkedIn" redirects the browser to LinkedIn's auth URL. LinkedIn redirects back to `/auth/callback?code=...`. That page posts `{ credential: <code> }` to `POST /auth/linkedin`.

Both flows receive a JWT access token in the response body (stored in memory) and a rolling refresh cookie (`sb_refresh`, httpOnly). The axios instance in `src/lib/api.ts` automatically attaches the token and retries with a refresh on 401.

---

## Project Structure

```
src/
├── app/
│   ├── (app)/           # Authenticated shell — chat, library, quiz, summaries
│   │   └── layout.tsx   # Auth guard + sidebar navigation
│   ├── auth/
│   │   └── callback/    # OAuth redirect handler (LinkedIn)
│   ├── login/           # Public login page (Google + LinkedIn buttons)
│   └── page.tsx         # Root redirect
├── components/
│   └── auth/
│       └── AuthProvider.tsx  # Rehydrates session from refresh cookie on mount
└── lib/
    ├── api.ts           # Axios instance (auth header, 401 retry interceptor)
    ├── auth.ts          # loginWithGoogle, loginWithLinkedIn, initiateLinkedInLogin, logout, refreshSession
    ├── store.ts         # Zustand store — user + isLoading
    └── types.ts         # Shared TypeScript interfaces
```

---

## Commands

```bash
npm run dev     # dev server at http://localhost:3000
npm run build   # production build
npm run lint    # ESLint
```
