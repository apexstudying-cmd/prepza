CREATE TABLE view_progress (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "user"(id),
    content_item_id INTEGER NOT NULL REFERENCES content_item(id),
    page_num INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_view_progress_user_item UNIQUE (user_id, content_item_id)
);
