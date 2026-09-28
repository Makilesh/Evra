-- 0001_init: Phase 1 schema. Source: BUILD.md §8.2 (keep in sync).
CREATE TABLE meeting (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, started_at INTEGER NOT NULL, ended_at INTEGER,
  mode TEXT NOT NULL DEFAULT 'one_on_one',                     -- one_on_one|meeting|solo
  situation TEXT,                                             -- call_headphones|call_speakers|in_person|hybrid
  language TEXT NOT NULL DEFAULT 'en', template TEXT NOT NULL,
  state TEXT NOT NULL,                                        -- recording|processing|ready|failed
  audio_keep_until INTEGER, keep_forever INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE TABLE audio_segment (
  id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL REFERENCES meeting(id) ON DELETE CASCADE,
  channel INTEGER NOT NULL, kind TEXT NOT NULL,               -- raw|opus
  start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL, path TEXT NOT NULL, deleted_at INTEGER
);
CREATE TABLE gap (
  id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL REFERENCES meeting(id) ON DELETE CASCADE,
  channel INTEGER, start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL, cause TEXT NOT NULL
);
CREATE TABLE transcript_version (
  id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL REFERENCES meeting(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,                                         -- live|fast|accurate
  model TEXT NOT NULL, created_at INTEGER NOT NULL, is_current INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE utterance (
  id TEXT PRIMARY KEY, version_id TEXT NOT NULL REFERENCES transcript_version(id) ON DELETE CASCADE,
  meeting_id TEXT NOT NULL, seq INTEGER NOT NULL, channel INTEGER NOT NULL,
  speaker_id TEXT, start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL,
  text TEXT NOT NULL, words_json TEXT, confidence REAL, origin TEXT NOT NULL DEFAULT 'human' -- human|evra
);
CREATE INDEX utt_meeting ON utterance(meeting_id, version_id, start_ms);
CREATE TABLE person (id TEXT PRIMARY KEY, display_name TEXT NOT NULL, is_owner INTEGER NOT NULL DEFAULT 0);
CREATE TABLE voiceprint (
  id TEXT PRIMARY KEY, person_id TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  model TEXT NOT NULL, centroid BLOB NOT NULL, n_samples INTEGER NOT NULL,
  locked INTEGER NOT NULL DEFAULT 0, updated_at INTEGER NOT NULL
);
CREATE TABLE speaker (
  id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL REFERENCES meeting(id) ON DELETE CASCADE,
  namespace TEXT NOT NULL,                                    -- room|remote|evra
  label TEXT NOT NULL, person_id TEXT REFERENCES person(id), match_score REAL, source TEXT
);
CREATE TABLE note_block (
  id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL REFERENCES meeting(id) ON DELETE CASCADE,
  position INTEGER NOT NULL, text TEXT NOT NULL, captured_at_ms INTEGER,
  phase TEXT NOT NULL,                                        -- before|during|after
  is_context INTEGER NOT NULL DEFAULT 0, aligned_json TEXT    -- [{utterance_id, score}]
);
CREATE TABLE generation (
  id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL REFERENCES meeting(id) ON DELETE CASCADE,
  created_at INTEGER NOT NULL, llm_provider TEXT NOT NULL, llm_model TEXT NOT NULL,
  prompt_version TEXT NOT NULL, template TEXT NOT NULL, transcript_version_id TEXT NOT NULL,
  tokens_in INTEGER, tokens_out INTEGER, dropped_claims INTEGER, is_current INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE output_block (
  id TEXT PRIMARY KEY, generation_id TEXT NOT NULL REFERENCES generation(id) ON DELETE CASCADE,
  meeting_id TEXT NOT NULL, section TEXT NOT NULL, position INTEGER NOT NULL,
  text TEXT NOT NULL, citations_json TEXT NOT NULL,
  provenance TEXT NOT NULL,                                   -- generated|edited|user
  base_text TEXT
);
CREATE TABLE action_item (
  id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL REFERENCES meeting(id) ON DELETE CASCADE,
  generation_id TEXT, text TEXT NOT NULL, owner_speaker_id TEXT, due TEXT,
  status TEXT NOT NULL DEFAULT 'open', confidence REAL, citations_json TEXT NOT NULL
);
CREATE TABLE decision (
  id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL REFERENCES meeting(id) ON DELETE CASCADE,
  generation_id TEXT, text TEXT NOT NULL, made_by_speaker_id TEXT, citations_json TEXT NOT NULL
);
CREATE TABLE open_question (
  id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL REFERENCES meeting(id) ON DELETE CASCADE,
  generation_id TEXT, text TEXT NOT NULL, raised_by_speaker_id TEXT, citations_json TEXT NOT NULL
);
CREATE TABLE topic (
  id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL REFERENCES meeting(id) ON DELETE CASCADE,
  generation_id TEXT, label TEXT NOT NULL, start_ms INTEGER, end_ms INTEGER,
  salience REAL, is_key_moment INTEGER DEFAULT 0
);
CREATE TABLE job (
  id TEXT PRIMARY KEY, type TEXT NOT NULL, meeting_id TEXT, payload_json TEXT NOT NULL,
  state TEXT NOT NULL,                                        -- queued|running|done|failed|dead
  priority INTEGER NOT NULL DEFAULT 5, attempts INTEGER NOT NULL DEFAULT 0,
  run_after INTEGER NOT NULL, error TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX job_ready ON job(state, priority, run_after);
