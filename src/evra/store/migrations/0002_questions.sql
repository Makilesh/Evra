CREATE TABLE question (
  id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL REFERENCES meeting(id) ON DELETE CASCADE,
  asked_at INTEGER NOT NULL, text TEXT NOT NULL,
  state TEXT NOT NULL,                                        -- asking|answered|not_found|unchecked|failed
  answer_json TEXT,                                           -- [{"text": ..., "citations": [utterance ids]}]
  reason TEXT, excerpt INTEGER NOT NULL DEFAULT 0,
  llm_model TEXT, prompt_version TEXT, transcript_version_id TEXT,
  tokens_in INTEGER, tokens_out INTEGER, dropped_claims INTEGER, seconds REAL
);
CREATE INDEX question_meeting ON question(meeting_id, asked_at);
