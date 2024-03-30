from dataclasses import dataclass
from typing import List, Optional

@dataclass
class ComarcaData:
    comarca: str
    capital: Optional[str] = None
    map_url: Optional[str] = None
    escut_url: Optional[str] = None
    MEDIA_FILES = ["map_url", "escut_url"]