-- 006_drop_dead_tables.sql
--
-- These tables are not referenced anywhere in app/ (verified by grep
-- across the whole codebase) -- leftovers from earlier iterations that
-- were superseded but never cleaned up:
--
--   metric_configs, metric_definitions, enabled_metrics
--     -> superseded by metric_catalog
--   alert_rules
--     -> superseded by thresholds
--   dashboards, dashboard_panels
--     -> unfinished feature, no route ever reads/writes them
--   account_permissions, user_accounts, user_roles
--     -> superseded by user_account_access + users.role
--   roles
--     -> role is just a varchar column on users; this lookup table
--        was never joined against anywhere
--
-- Back these up first (mysqldump) if you want to keep them for
-- reference -- they're empty or stale in every environment checked.

DROP TABLE IF EXISTS metric_configs;
DROP TABLE IF EXISTS metric_definitions;
DROP TABLE IF EXISTS enabled_metrics;
DROP TABLE IF EXISTS alert_rules;
DROP TABLE IF EXISTS dashboard_panels;
DROP TABLE IF EXISTS dashboards;
DROP TABLE IF EXISTS account_permissions;
DROP TABLE IF EXISTS user_accounts;
DROP TABLE IF EXISTS user_roles;
DROP TABLE IF EXISTS roles;
