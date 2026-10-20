import tempfile
from pathlib import Path


def make_home():
    """A temp home folder shaped like the PurrOS samples. Returns (TemporaryDirectory, Path)."""
    td = tempfile.TemporaryDirectory()
    h = Path(td.name)
    for d in ("Documents", "Downloads", "Music", "Pictures", "Videos"):
        (h / d).mkdir()
    (h / "notes.txt").write_text("call mom sunday\nfix the porch light\ntry the new ramen place\n")
    (h / "grocery-list.txt").write_text("eggs\ncoffee\n")
    (h / "beach-sunset.mp4").write_bytes(b"\0" * 16)
    (h / "Documents" / "taxes-2025.pdf").write_bytes(b"%PDF-1.4\n")
    (h / "Documents" / "resume.docx").write_bytes(b"PK")
    (h / "Pictures" / "cabin-in-snow.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (h / "Videos" / "beach-sunset.mp4").write_bytes(b"\0" * 16)
    (h / ".hidden").write_text("x")
    return td, h
