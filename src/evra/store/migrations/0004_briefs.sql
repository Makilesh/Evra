-- 0004_briefs: a person's prep brief (Plan C, A13), written from the notes of their recent 1:1s.
-- points_json = [{"text", "meetings": [meeting ids it cites]}]; meetings_json = the meetings it
-- was written from, newest first. Forgetting the person deletes it (D14).
-- Source: BUILD.md §8.2 (keep in sync).
CREATE TABLE brief (id TEXT PRIMARY KEY, person_id TEXT NOT NULL REFERENCES person(id) ON DELETE CASCADE, created_at INTEGER NOT NULL,
  points_json TEXT NOT NULL, meetings_json TEXT NOT NULL, llm_model TEXT, prompt_version TEXT);
CREATE INDEX brief_person ON brief(person_id, created_at);
