from enum import Enum

class FileType(str, Enum):
    PDF = "PDF"
    XML = "XML"

    @classmethod
    def from_filename(cls, filename: str) -> "FileType":
        ext = filename.rsplit(".", 1)[-1].upper()
        if ext == "PDF":
            return cls.PDF
        if ext == "XML":
            return cls.XML
        raise ValueError(f"Unsupported file type: .{ext}")