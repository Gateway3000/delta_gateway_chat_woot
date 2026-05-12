from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class UploadedAttachment(BaseModel):
    kind: Literal["uploaded"] = "uploaded"
    signed_id: str


class LocalFileAttachment(BaseModel):
    kind: Literal["local_file"] = "local_file"
    filename: str
    mime_type: str
    file_type: str = "file"
    temp_file_path: Path


class Base64Attachment(BaseModel):
    kind: Literal["base64"] = "base64"
    filename: str
    mime_type: str
    file_type: str = "file"
    data: str
    data_encoding: str = "base64"


ChatwootAttachment = UploadedAttachment | LocalFileAttachment | Base64Attachment
