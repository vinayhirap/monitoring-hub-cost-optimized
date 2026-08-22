-- 004_metrics_last_value_only.sql
--
-- `metrics` was accidentally storing full history (a new row every
-- collection cycle) instead of just the latest value per resource+metric.
-- That's a duplicate of what VictoriaMetrics already stores permanently,
-- and the only consumer (alert_evaluator.py) ever reads is the latest
-- value anyway. This migration collapses the table down to one row per
-- (resource_id, metric_name) and adds a UNIQUE key so future writes
-- upsert in place instead of accumulating rows again.
--
-- Safe to run on a live table. Back up first if you want to keep the
-- old history for audit purposes (it's redundant with VM, but harmless
-- to export before dropping).
--
-- The live table is partitioned (a leftover from when it stored full
-- history), and MySQL requires any UNIQUE KEY to include the
-- partitioning column(s). Since this table is now a last-value cache
-- with no history to prune, time-based partitioning no longer serves a
-- purpose here, so step 0 removes it. This is written to be safe on
-- both partitioned and non-partitioned installs.

-- 0. Drop partitioning if present (no-op if the table isn't partitioned).
SET @has_partitions := (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.PARTITIONS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME   = 'metrics'
    AND PARTITION_NAME IS NOT NULL
);
SET @sql := IF(@has_partitions > 0, 'ALTER TABLE metrics REMOVE PARTITIONING', 'DO 0');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 1. Collapse existing rows: keep only the most recent row per pair.
DELETE m1 FROM metrics m1
JOIN metrics m2
  ON m1.resource_id  = m2.resource_id
 AND m1.metric_name  = m2.metric_name
 AND (
       m1.metric_timestamp < m2.metric_timestamp
    OR (m1.metric_timestamp = m2.metric_timestamp AND m1.id < m2.id)
     );

-- 2. Prevent future duplicates: one row per resource+metric, upserted.
SET @has_unique_key := (
  SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME   = 'metrics'
    AND INDEX_NAME   = 'uniq_metrics_resource_metric'
);
SET @sql := IF(@has_unique_key = 0,
  'ALTER TABLE metrics ADD UNIQUE KEY uniq_metrics_resource_metric (resource_id, metric_name)',
  'DO 0');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 3. Reclaim the space freed by the deleted history rows.
OPTIMIZE TABLE metrics;
