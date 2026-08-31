# Voice Journal Frontend - Production Checklist

## Pre-Deployment

### 1. Environment Setup
```bash
cd web/frontend
npm ci
```

### 2. Build
```bash
npm run build
# Output: web/dist/
```

### 3. Deploy
```bash
# On laptop
cd ~/voice_journal_src
git pull
cd web/frontend
npm ci
npm run build
# Restart Flask (which serves the built assets)
systemctl --user restart voice-journal
# or
pkill -f "python.*app.py" && python web/app.py &
```

## Configuration

### Environment Variables (Optional)

Create `.env.local` for local development:
```
VITE_API_URL=http://localhost:5000
```

### Flask Production Settings

For production, set:
```python
app.run(host='0.0.0.0', port=5000, debug=False)
```

## Verification

1. Visit `http://100.99.161.57:5000/`
2. Check Dashboard loads
3. Test navigation (Journal, Settings)
4. Verify live updates connect (green status)
5. Test conversation detail modal

## Troubleshooting

### Build Errors
```bash
rm -rf node_modules
npm install
npm run build
```

### Blank Page
- Check browser console for errors
- Verify Flask serves index.html
- Check static route in app.py

### API Errors
- Verify Flask is running
- Check CORS headers
- Verify database exists at `data/voice_journal.db`
