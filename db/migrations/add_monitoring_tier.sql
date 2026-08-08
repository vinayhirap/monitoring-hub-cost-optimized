-- db/migrations/add_monitoring_tier.sql
-- Phase 2: Add monitoring_tier to resources table
-- Run: mysql -umonitor -proot123 monitoring_hub < db/migrations/add_monitoring_tier.sql

ALTER TABLE resources
    ADD COLUMN monitoring_tier ENUM('critical', 'standard', 'low')
    NOT NULL DEFAULT 'standard'
    AFTER instance_state;

UPDATE resources SET monitoring_tier = 'critical' WHERE resource_type = 'rds';
UPDATE resources SET monitoring_tier = 'critical' WHERE resource_type = 'elb';
UPDATE resources SET monitoring_tier = 'low'      WHERE resource_type = 'ebs';
UPDATE resources SET monitoring_tier = 'low'      WHERE resource_type = 'lambda';
UPDATE resources SET monitoring_tier = 'low'
    WHERE resource_type = 'ec2' AND instance_state != 'running';

ALTER TABLE resources
    ADD INDEX idx_resources_tier (aws_account_id, monitoring_tier, instance_state);