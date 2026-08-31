# Voice Journal Frontend

Modern React dashboard for the Voice Journal application.

## Tech Stack

- **React 18** with TypeScript
- **Vite** for fast development and builds
- **Tailwind CSS** with custom earth-tones theme
- **Radix UI** components (shadcn/ui style)
- **Recharts** for analytics
- **Framer Motion** for animations
- **TanStack Query** for data fetching

## Development

```bash
# Install dependencies
npm install

# Start dev server (proxies API to Flask on port 5000)
npm run dev

# Build for production
npm run build
# Outputs to ../dist/
```

## Color Palette

Earth tones for a warm, personal feel:

| Token     | Light       | Dark        |
|-----------|-------------|-------------|
| Primary   | `#8B7355`   | `#B8A085`   |
| Secondary | `#CD853F`   | `#E09837`   |
| Accent    | `#556B2F`   | `#94A261`   |
| Background| `#FDF8F3`   | `#2A1E12`   |
| Text      | `#3D2914`   | `#FDF8F3`   |

## Project Structure

```
src/
├── components/
│   ├── ui/          # Base UI components (Button, Card, etc.)
│   ├── layout/      # App shell (Header, Sidebar)
│   ├── dashboard/   # Dashboard widgets
│   └── conversations/ # Conversation browser components
├── lib/             # API client, utilities
├── hooks/           # Custom React hooks
└── pages/           # Route pages
```

## API Integration

All API endpoints are proxied through Vite dev server to Flask:

- `GET /api/stats` - Today's statistics
- `GET /api/conversations` - List conversations
- `GET /api/conversation/:id` - Single conversation
- `GET /api/search?q=query` - Search
- `GET /api/weekly_summary` - Weekly data
- `GET /api/shivangi_stats` - Shivangi conversation metrics
- `GET /api/stream` - SSE for real-time updates

## Deployment

The production build is served directly by Flask:

```bash
cd web/frontend
npm ci
npm run build
# Restart Flask app
```
