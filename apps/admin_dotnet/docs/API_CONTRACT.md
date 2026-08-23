# Expected Admin API Contract

Recommended dedicated endpoints:

```text
GET  /admin/dashboard
GET  /admin/users
POST /admin/users/{id}/suspend
POST /admin/users/{id}/reactivate
POST /admin/users/{id}/sessions/revoke
GET  /admin/jobs
POST /admin/jobs/{id}/cancel
GET  /admin/incidents
POST /admin/incidents/{id}/assign
POST /admin/incidents/{id}/resolve
GET  /admin/quarantine
POST /admin/quarantine/{id}/release
DELETE /admin/quarantine/{id}
GET  /admin/audit
GET  /admin/health
```

Every endpoint must enforce administrative roles server-side. Hiding buttons in the UI is not authorization.
