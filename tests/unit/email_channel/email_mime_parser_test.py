from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from channels.email_channel import EmailMimeParser


def _make_email(
    from_addr: str = "user@example.com",
    to_addr: str = "support@example.com",
    subject: str = "Test Subject",
    text_body: str = "Hello World",
    message_id: str = "<test@example.com>",
) -> bytes:
    msg = MIMEMultipart("alternative")
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["Message-ID"] = message_id

    msg.attach(MIMEText(text_body, "plain", "utf-8"))

    return msg.as_bytes()


class TestEmailMimeParser:
    def test_parse_simple_email(self) -> None:
        raw = _make_email(
            from_addr="John Doe <john@example.com>",
            subject="Hello",
            text_body="Plain text body",
        )

        parsed = EmailMimeParser.parse_raw_email(raw)

        assert parsed.from_email == "john@example.com"
        assert parsed.from_name == "John Doe"
        assert parsed.to == "support@example.com"
        assert parsed.subject == "Hello"
        assert parsed.text_body == "Plain text body"
        assert parsed.message_id == "<test@example.com>"

    def test_parse_email_without_message_id(self) -> None:
        raw = _make_email(message_id="")
        parsed = EmailMimeParser.parse_raw_email(raw)
        assert parsed.message_id == ""

    def test_parse_email_address_bare_email(self) -> None:
        email_addr, name = EmailMimeParser._parse_address("user@example.com")
        assert email_addr == "user@example.com"
        assert name == ""

    def test_parse_email_address_empty(self) -> None:
        email_addr, name = EmailMimeParser._parse_address("")
        assert email_addr == ""
        assert name == ""

    def test_parse_email_address_no_at(self) -> None:
        email_addr, name = EmailMimeParser._parse_address("Just a name")
        assert email_addr == ""
        assert name == "Just a name"

    def test_decode_header_value_plain(self) -> None:
        result = EmailMimeParser._decode_header_value("Simple Subject")
        assert result == "Simple Subject"

    def test_decode_header_value_none(self) -> None:
        result = EmailMimeParser._decode_header_value(None)
        assert result == ""

    def test_decode_header_value_encoded(self) -> None:
        result = EmailMimeParser._decode_header_value("=?utf-8?q?Hello?=")
        assert "Hello" in result

    def test_parse_email_with_html(self) -> None:
        msg = MIMEMultipart("alternative")
        msg["From"] = "user@example.com"
        msg["To"] = "support@example.com"
        msg["Subject"] = "HTML Test"
        msg.attach(MIMEText("Plain text", "plain", "utf-8"))
        msg.attach(MIMEText("<p>HTML text</p>", "html", "utf-8"))
        raw = msg.as_bytes()

        parsed = EmailMimeParser.parse_raw_email(raw)
        assert parsed.text_body == "Plain text"
        assert "<p>HTML text</p>" in parsed.html_body

    def test_parse_email_non_multipart_text(self) -> None:
        msg = MIMEText("Simple body", "plain", "utf-8")
        msg["From"] = "user@example.com"
        raw = msg.as_bytes()

        parsed = EmailMimeParser.parse_raw_email(raw)
        assert parsed.text_body == "Simple body"

    def test_parse_email_non_multipart_html(self) -> None:
        msg = MIMEText("<p>HTML body</p>", "html", "utf-8")
        msg["From"] = "user@example.com"
        raw = msg.as_bytes()

        parsed = EmailMimeParser.parse_raw_email(raw)
        assert "<p>HTML body</p>" in parsed.html_body

    def test_parse_email_with_date(self) -> None:
        import time

        msg = MIMEMultipart()
        msg["From"] = "user@example.com"
        msg["To"] = "support@example.com"
        msg["Subject"] = "Date Test"
        msg["Date"] = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())
        text_part = MIMEText("Body", "plain", "utf-8")
        msg.attach(text_part)
        raw = msg.as_bytes()

        parsed = EmailMimeParser.parse_raw_email(raw)
        assert parsed.date is not None

    def test_parse_email_with_invalid_date(self) -> None:
        msg = MIMEMultipart()
        msg["From"] = "user@example.com"
        msg["Date"] = "Invalid Date String"
        raw = msg.as_bytes()

        parsed = EmailMimeParser.parse_raw_email(raw)
        assert parsed.date is None

    def test_parse_email_with_attachments(self) -> None:
        msg = MIMEMultipart()
        msg["From"] = "user@example.com"
        msg["To"] = "support@example.com"
        msg["Subject"] = "With Attachment"

        text_part = MIMEText("See attached", "plain", "utf-8")
        msg.attach(text_part)

        pdf_part = MIMEApplication(b"PDF content", Name="doc.pdf")
        pdf_part["Content-Disposition"] = 'attachment; filename="doc.pdf"'
        msg.attach(pdf_part)

        raw = msg.as_bytes()
        parsed = EmailMimeParser.parse_raw_email(raw)

        assert len(parsed.attachments) == 1
        assert parsed.attachments[0]["filename"] == "doc.pdf"
        assert parsed.attachments[0]["content_type"] == "application/octet-stream"
        assert parsed.attachments[0]["size"] == len(b"PDF content")

    def test_parse_email_skips_attachments_in_bodies(self) -> None:
        msg = MIMEMultipart()
        msg["From"] = "user@example.com"

        attachment_part = MIMEApplication(b"data", Name="test.txt")
        attachment_part["Content-Disposition"] = "attachment; filename=test.txt"
        msg.attach(attachment_part)

        raw = msg.as_bytes()
        parsed = EmailMimeParser.parse_raw_email(raw)

        assert parsed.text_body == ""
        assert parsed.html_body == ""

    def test_capture_raw_headers(self) -> None:
        msg = MIMEMultipart()
        msg["From"] = "user@example.com"
        msg["To"] = "support@example.com"
        msg["Subject"] = "Headers Test"
        msg["X-Custom-Header"] = "Custom Value"
        msg["Message-ID"] = "<test@example.com>"
        raw = msg.as_bytes()

        parsed = EmailMimeParser.parse_raw_email(raw)
        assert "X-Custom-Header" in parsed.raw_headers
        assert parsed.raw_headers["X-Custom-Header"] == "Custom Value"
        assert "Message-ID" not in parsed.raw_headers
        assert "From" not in parsed.raw_headers

    def test_parse_email_attachment_no_filename(self) -> None:
        msg = MIMEMultipart()
        msg["From"] = "user@example.com"

        part = MIMEApplication(b"data")
        part["Content-Disposition"] = "attachment"
        msg.attach(part)

        raw = msg.as_bytes()
        parsed = EmailMimeParser.parse_raw_email(raw)
        assert len(parsed.attachments) == 0

    def test_parse_email_attachment_empty_payload(self) -> None:
        msg = MIMEMultipart()
        msg["From"] = "user@example.com"

        part = MIMEApplication(b"")
        part["Content-Disposition"] = 'attachment; filename="empty.txt"'
        msg.attach(part)

        raw = msg.as_bytes()
        parsed = EmailMimeParser.parse_raw_email(raw)
        assert len(parsed.attachments) == 0
