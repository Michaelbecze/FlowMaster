# Phase 1 Data Model: Enterprise NetFlow Collection & Analytics Platform

Entities are grouped by the store they live in (see `research.md` #1–#3 for the storage
decisions). Fields are drawn from the spec's Key Entities and Functional Requirements;
this is a logical model, not a DDL/migration script.

## ClickHouse — flow analytics store

### FlowRecord
The fundamental unit of collected data (spec Key Entities; FR-001).

| Field | Type | Notes |
|---|---|---|
| `timestamp` | DateTime64 | When the flow was observed; primary ordering key |
| `site_id` | UUID/String | FK-like reference to Site (identity service) — attributes every record to its origin (FR-001) |
| `src_addr`, `dst_addr` | IP | Source/destination address |
| `src_port`, `dst_port` | UInt16 | Source/destination port |
| `protocol` | UInt8 | IP protocol number |
| `application` | LowCardinality(String) | Derived application label (port-mapping, extensible) |
| `bytes`, `packets` | UInt64 | Volume counters |
| `direction` | Enum8 | Inbound/outbound relative to site, if determinable |
| `ingested_at` | DateTime64 | When the platform received the flow (distinct from `timestamp`, supports lag/backlog visibility for FR-014) |

**Retention**: governed by `RetentionPolicy` (below); ClickHouse TTL configured per the
organization's configured retention window (FR-005). Deletion is a declared TTL, not a
silent ad hoc purge, so it stays consistent with FR-005's "MUST NOT silently delete
outside of configured policy."

**Validation rules**: rows failing structural validation (truncated/malformed source
packet) are rejected at the Ingestion service (FR-015) and never reach this table;
malformed-packet counts are emitted as a metric, not written as FlowRecords.

## PostgreSQL — relational metadata store

### Organization
Spec: single top-level boundary for v1 (FR-021). One row for v1, modeled as a real table
(not a hardcoded constant) so a later multi-tenant release does not require a schema
rewrite — this does not add multi-tenant behavior now, only avoids foreclosing it later.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `name` | String | Display name |
| `retention_policy_id` | FK → RetentionPolicy | |

### Site
A monitored location/device sending flow data (spec Key Entities; FR-010).

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | PK; referenced by `FlowRecord.site_id` |
| `organization_id` | FK → Organization | |
| `name` | String | |
| `network_identity` | String | Exporter source IP/identifier used to attribute inbound flows |
| `status` | Enum | `active` \| `stale` \| `never_connected` — drives FR-004's visible offline indicator |
| `last_seen_at` | Timestamp, nullable | Null until first flow received; distinguishes "never connected" from "went silent" (Edge Cases) |
| `created_at`, `created_by` | Timestamp, FK → User | Audit trail source data |

### User
| Field | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `organization_id` | FK → Organization | |
| `email` | String, unique | Login identifier |
| `password_hash` | String | Platform-managed credential (FR-020); nullable if/when SSO is added later without a schema break |
| `status` | Enum | `active` \| `disabled` |
| `created_at` | Timestamp | |

### Role
| Field | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `name` | Enum/String | e.g., Viewer, Analyst, Administrator (spec Key Entities) |
| `permissions` | String[] / JSONB | Set of permitted actions |

### UserRoleAssignment
Join entity — a user can hold a role scoped to a subset of sites (FR-008).

| Field | Type | Notes |
|---|---|---|
| `user_id` | FK → User | |
| `role_id` | FK → Role | |
| `site_id` | FK → Site, nullable | Null = organization-wide scope for that role |

### Report
A saved or ad hoc filtered query over historical flow data (spec Key Entities; FR-006/FR-007).

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `owner_user_id` | FK → User | |
| `filter_definition` | JSONB | Time range, site(s), protocol, application, host filters |
| `name` | String, nullable | Present for saved reports; null for ad hoc/one-off exports |
| `created_at` | Timestamp | |

### AlertRule
Condition defined over flow data (spec Key Entities; FR-012).

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `owner_user_id` | FK → User | |
| `site_scope` | FK → Site, nullable | Null = all sites the owner can access |
| `condition_definition` | JSONB | Threshold/pattern definition |
| `notification_target` | String/JSONB | Where to deliver (email, webhook, etc.) |
| `enabled` | Boolean | |

### AlertEvent
A firing of an AlertRule — supports FR-013's suppression of duplicate notifications for
an ongoing condition.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `alert_rule_id` | FK → AlertRule | |
| `triggered_at` | Timestamp | |
| `resolved_at` | Timestamp, nullable | Null while condition remains true (drives de-dup) |
| `triggering_flow_reference` | String | Pointer/query used to retrieve the underlying flow data (FR-012's "see the underlying flow data that triggered it") |

### AuditLogEntry
Record of an administrative/config-changing action (spec Key Entities; FR-011).

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `actor_user_id` | FK → User | |
| `action` | String | e.g., `site.created`, `user.role_changed`, `retention_policy.updated` |
| `target` | String | Identifier of the affected entity |
| `occurred_at` | Timestamp | |
| `detail` | JSONB | Before/after or relevant context |

### RetentionPolicy
| Field | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `organization_id` | FK → Organization | |
| `duration_days` | Integer | Configurable per FR-005 |
| `updated_at`, `updated_by` | Timestamp, FK → User | |

## Redis — ephemeral real-time state (not a system of record)

- **Rolling aggregate cache**: keyed by `site_id`/organization scope, holding the current
  window's traffic volume, protocol mix, and top-talkers used to serve SC-001's 5-second
  update target without re-querying ClickHouse per tick.
- **WebSocket fan-out channel**: pub/sub topic(s) the Realtime service publishes to and
  the Gateway subscribes to per connected dashboard client.
- **Alert de-dup state**: `alert_rule_id` → last-notified timestamp / active-state flag,
  implementing FR-013.
- **API rate-limit counters**: per API token, supporting FR-019.

None of this state is authoritative — it is rebuildable from ClickHouse/PostgreSQL/the
event stream, consistent with FR-005/FR-011's requirement that the real systems of record
never lose data silently.

## Relationships summary

```
Organization 1──* Site 1──* FlowRecord   (Site is the join between metadata and flow data)
Organization 1──* User *──* Role          (via UserRoleAssignment, optionally scoped to a Site)
User 1──* Report
User 1──* AlertRule 1──* AlertEvent
User 1──* AuditLogEntry (as actor)
Organization 1──1 RetentionPolicy
```
