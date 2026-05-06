from typing import Self

from pydantic import BaseModel, model_validator

from src import Settings


class SmtpConfig(BaseModel):
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str
    smtp_password: str | None = None
    smtp_from: str
    smtp_use_tls: bool = True


class MailboxConfig(BaseModel):
    connector_id: str
    cw_account_id: str
    cw_inbox_id: str
    imap_username: str
    imap_password: str
    smtp: SmtpConfig
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_mailbox: str = "INBOX"
    imap_use_ssl: bool = True
    processed_folder: str | None = None

    @model_validator(mode="after")
    def set_default_smtp_password(self) -> Self:
        if self.smtp.smtp_password is None:
            self.smtp.smtp_password = self.imap_password
        return self


class EmailSettings(Settings):
    mailboxes_config: list[MailboxConfig] = []
    channel_upload_max_mb: int = 20
    poll_interval_seconds: float = 5.0
