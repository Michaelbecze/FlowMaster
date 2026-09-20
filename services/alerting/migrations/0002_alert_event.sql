-- AlertEvent: a firing of an AlertRule (data-model.md). resolved_at stays NULL while
-- the condition remains continuously true — this is what FR-013's de-dup means in
-- storage: one open row per active condition, not one row per evaluation tick.
CREATE TABLE alert_event (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_rule_id             UUID NOT NULL REFERENCES alert_rule(id) ON DELETE CASCADE,
    triggered_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at               TIMESTAMPTZ NULL,
    triggering_flow_reference JSONB NOT NULL
);

CREATE INDEX alert_event_rule_idx ON alert_event (alert_rule_id, triggered_at DESC);
