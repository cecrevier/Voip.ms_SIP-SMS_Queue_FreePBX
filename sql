USE asterisk;
Create the queue table:
CREATE TABLE sms_queue (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    ext VARCHAR(20) NOT NULL,
    src VARCHAR(255) NOT NULL,
    dst VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    status ENUM('queued','sending','sent','failed') NOT NULL DEFAULT 'queued',
    tries INT NOT NULL DEFAULT 0,
    last_error VARCHAR(255) DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at DATETIME DEFAULT NULL,
    PRIMARY KEY (id),
    KEY idx_ext_status (ext, status),
    KEY idx_status_created (status, created_at)
);
