-- 005_password_reset_tokens.sql
-- Supports POST /api/auth/forgot-password and /api/auth/reset-password.
-- One active token per user (old ones are deleted when a new one is
-- requested); expired/used tokens are deleted, so this table stays tiny.

CREATE TABLE IF NOT EXISTS password_reset_tokens (
  id         BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id    BIGINT NOT NULL,
  token      VARCHAR(255) NOT NULL,
  expires_at DATETIME NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uniq_prt_token (token),
  KEY idx_prt_user (user_id),
  CONSTRAINT fk_prt_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
