-- Indexes for bounded affected-key closure queries, not a second source authority.
CREATE INDEX clean_assertion_subject ON mdm_v2.assertion ((body->>'subject'));
CREATE INDEX clean_decision_subject ON mdm_v2.decision ((body->>'subject'));
CREATE INDEX clean_decision_entity ON mdm_v2.decision ((body->>'entity_id'));
CREATE INDEX clean_decision_left ON mdm_v2.decision ((body->>'left'));
CREATE INDEX clean_decision_right ON mdm_v2.decision ((body->>'right'));
CREATE INDEX clean_decision_target ON mdm_v2.decision ((body->>'target'));
