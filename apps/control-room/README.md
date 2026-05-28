# TSF Control Room

Game-style frontend for The Synthetic Firm. It visualizes Atlas, Scout, Forge,
Pulse, and Sentinel in a birdview office with tasks, approvals, runtime state,
budget, reports, and events.

```bash
npm install
npm run dev
npm run build
npm run typecheck
```

Phase 8A uses local mock state only. It does not call provider APIs, store
secrets, execute approvals, or run external business automation.
