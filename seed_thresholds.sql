-- seed_thresholds.sql
-- Run this to populate metric_catalog and thresholds for all services
-- Safe to run multiple times (uses INSERT IGNORE)

-- ── 1. Metric Catalog ─────────────────────────────────────────
-- Defines all collectable metrics per service

INSERT IGNORE INTO metric_catalog (service, metric_name, namespace, statistic, unit, default_interval, enabled) VALUES
-- EC2
('ec2', 'cpuutilization',  'AWS/EC2', 'Average', 'Percent',  60, 1),
('ec2', 'networkin',       'AWS/EC2', 'Average', 'Bytes',    60, 1),
('ec2', 'networkout',      'AWS/EC2', 'Average', 'Bytes',    60, 1),
('ec2', 'diskreadbytes',   'AWS/EC2', 'Average', 'Bytes',    60, 1),
('ec2', 'diskwritebytes',  'AWS/EC2', 'Average', 'Bytes',    60, 1),
-- EBS
('ebs', 'volumereadops',    'AWS/EBS', 'Average', 'Count',   60, 1),
('ebs', 'volumewriteops',   'AWS/EBS', 'Average', 'Count',   60, 1),
('ebs', 'volumereadbytes',  'AWS/EBS', 'Average', 'Bytes',   60, 1),
('ebs', 'volumewritebytes', 'AWS/EBS', 'Average', 'Bytes',   60, 1),
('ebs', 'volumequeuelength','AWS/EBS', 'Average', 'Count',   60, 1),
('ebs', 'burstbalance',     'AWS/EBS', 'Average', 'Percent', 60, 1),
-- RDS
('rds', 'cpuutilization',  'AWS/RDS', 'Average', 'Percent',  60, 1),
('rds', 'dbconnections',   'AWS/RDS', 'Average', 'Count',    60, 1),
('rds', 'freestorage',     'AWS/RDS', 'Average', 'Bytes',    60, 1),
('rds', 'readiops',        'AWS/RDS', 'Average', 'Count/s',  60, 1),
('rds', 'writeiops',       'AWS/RDS', 'Average', 'Count/s',  60, 1),
('rds', 'readlatency',     'AWS/RDS', 'Average', 'Seconds',  60, 1),
('rds', 'writelatency',    'AWS/RDS', 'Average', 'Seconds',  60, 1),
('rds', 'freeablememory',  'AWS/RDS', 'Average', 'Bytes',    60, 1),
-- ELB
('elb', 'requestcount',    'AWS/ApplicationELB', 'Sum',     'Count',   60, 1),
('elb', 'errors5xx',       'AWS/ApplicationELB', 'Sum',     'Count',   60, 1),
('elb', 'errors4xx',       'AWS/ApplicationELB', 'Sum',     'Count',   60, 1),
('elb', 'responselatency', 'AWS/ApplicationELB', 'Average', 'Seconds', 60, 1),
('elb', 'healthyhosts',    'AWS/ApplicationELB', 'Average', 'Count',   60, 1),
('elb', 'unhealthyhosts',  'AWS/ApplicationELB', 'Average', 'Count',   60, 1),
-- ECS
('ecs_service', 'cpuutilization',  'AWS/ECS', 'Average', 'Percent', 60, 1),
('ecs_service', 'memutilization',  'AWS/ECS', 'Average', 'Percent', 60, 1),
-- Lambda
('lambda', 'invocations', 'AWS/Lambda', 'Sum',     'Count',   60, 1),
('lambda', 'errors',      'AWS/Lambda', 'Sum',     'Count',   60, 1),
('lambda', 'duration',    'AWS/Lambda', 'Average', 'Ms',      60, 1),
('lambda', 'throttles',   'AWS/Lambda', 'Sum',     'Count',   60, 1);


-- ── 2. Default Thresholds per account ────────────────────────
-- Seeds sensible production defaults for each account
-- Uses stored procedure pattern via INSERT ... SELECT

-- Get all account IDs and insert thresholds for each
INSERT IGNORE INTO thresholds
    (aws_account_id, resource_type, metric_id, warning_value, critical_value, comparison, evaluation_period, enabled)
SELECT
    a.id,
    mc.service,
    mc.id,
    defaults.warning_value,
    defaults.critical_value,
    defaults.comparison,
    5,
    1
FROM aws_accounts a
CROSS JOIN metric_catalog mc
JOIN (
    SELECT 'cpuutilization'   AS metric_name, 70  AS warning_value, 90  AS critical_value, '>'  AS comparison UNION ALL
    SELECT 'networkin',                        50000000, 100000000, '>'  UNION ALL
    SELECT 'networkout',                       50000000, 100000000, '>'  UNION ALL
    SELECT 'diskreadbytes',                    50000000, 100000000, '>'  UNION ALL
    SELECT 'diskwritebytes',                   50000000, 100000000, '>'  UNION ALL
    -- EBS
    SELECT 'volumereadops',                    1000, 5000,  '>'  UNION ALL
    SELECT 'volumewriteops',                   1000, 5000,  '>'  UNION ALL
    SELECT 'volumequeuelength',                1,    5,     '>'  UNION ALL
    SELECT 'burstbalance',                     30,   10,    '<'  UNION ALL
    -- RDS
    SELECT 'cpuutilization',                   70,   90,    '>'  UNION ALL
    SELECT 'dbconnections',                    80,   100,   '>'  UNION ALL
    SELECT 'freestorage',                      5368709120, 1073741824, '<'  UNION ALL  -- 5GB warn, 1GB crit
    SELECT 'readiops',                         1000, 3000,  '>'  UNION ALL
    SELECT 'writeiops',                        1000, 3000,  '>'  UNION ALL
    SELECT 'readlatency',                      0.02, 0.05,  '>'  UNION ALL  -- 20ms warn, 50ms crit
    SELECT 'writelatency',                     0.02, 0.05,  '>'  UNION ALL
    SELECT 'freeablememory',                   536870912, 268435456, '<'  UNION ALL  -- 512MB warn, 256MB crit
    -- ELB
    SELECT 'errors5xx',                        10,   50,    '>'  UNION ALL
    SELECT 'errors4xx',                        50,   200,   '>'  UNION ALL
    SELECT 'responselatency',                  1,    3,     '>'  UNION ALL  -- 1s warn, 3s crit
    SELECT 'unhealthyhosts',                   1,    2,     '>=' UNION ALL
    -- ECS
    SELECT 'cpuutilization',                   70,   90,    '>'  UNION ALL
    SELECT 'memutilization',                   75,   90,    '>'  UNION ALL
    -- Lambda
    SELECT 'errors',                           5,    20,    '>'  UNION ALL
    SELECT 'duration',                         5000, 10000, '>'  UNION ALL  -- 5s warn, 10s crit
    SELECT 'throttles',                        10,   50,    '>'
) defaults ON defaults.metric_name = mc.metric_name
WHERE a.status = 'active';