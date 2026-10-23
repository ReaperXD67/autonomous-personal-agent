BEGIN;

ALTER TABLE career_gmail_messages
    DROP CONSTRAINT IF EXISTS career_gmail_messages_suggested_status_check;
ALTER TABLE career_gmail_messages
    ADD CONSTRAINT career_gmail_messages_suggested_status_check CHECK (suggested_status IN (
        'submitted', 'acknowledgement', 'recruiter_reply', 'shortlisted', 'interview',
        'rejected', 'offer', 'withdrawn', 'needs_review'
    ));

ALTER TABLE career_application_events
    DROP CONSTRAINT IF EXISTS career_application_events_status_check;
ALTER TABLE career_application_events
    ADD CONSTRAINT career_application_events_status_check CHECK (status IN (
        'submitted', 'acknowledgement', 'recruiter_reply', 'shortlisted', 'interview',
        'rejected', 'offer', 'withdrawn', 'needs_review'
    ));

INSERT INTO schema_migrations (version) VALUES ('024_career_shortlist_tracking')
ON CONFLICT (version) DO NOTHING;
COMMIT;
