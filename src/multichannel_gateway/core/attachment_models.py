from typing import Literal

from pydantic import BaseModel


class UploadedAttachment(BaseModel):
    kind: Literal["uploaded"] = "uploaded"
    signed_id: str


class Base64Attachment(BaseModel):
    kind: Literal["base64"] = "base64"
    filename: str
    mime_type: str
    file_type: str = "file"
    data: str
    data_encoding: str = "base64"


ChatwootAttachment = UploadedAttachment | Base64Attachment
