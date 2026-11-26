-- 0003_items: action items, decisions and open questions are records (Plan B). An action item's
-- status is open | done | dismissed; the time the owner last changed it is kept, and a rewrite
-- carries it over to the matching new item. Source: BUILD.md §8.2 (keep in sync).
ALTER TABLE action_item ADD COLUMN status_changed_at INTEGER;
CREATE INDEX action_item_status ON action_item(status, meeting_id);
