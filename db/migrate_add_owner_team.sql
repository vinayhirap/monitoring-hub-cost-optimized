-- Migration: add owner_team and environment columns to aws_accounts
-- Run ONCE on server after deploying:
--   mysql -umonitor -proot123 monitoring_hub < db/migrate_add_owner_team.sql

ALTER TABLE aws_accounts
  ADD COLUMN IF NOT EXISTS owner_team  VARCHAR(100) NOT NULL DEFAULT '' AFTER description,
  ADD COLUMN IF NOT EXISTS environment VARCHAR(50)  NOT NULL DEFAULT 'PROD' AFTER owner_team;
