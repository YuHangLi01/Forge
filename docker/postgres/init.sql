-- Initialize schemas for Forge application
-- This runs once when the PostgreSQL container starts fresh

CREATE SCHEMA IF NOT EXISTS langgraph;
COMMENT ON SCHEMA langgraph IS 'LangGraph PostgresSaver checkpoint tables (auto-created by checkpointer.setup())';

CREATE SCHEMA IF NOT EXISTS forge;
COMMENT ON SCHEMA forge IS 'Forge business tables: tasks, user_profiles, event_processed';
