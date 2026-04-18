from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Any

class AdStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    CANCELED = "canceled"

class AdType(str, Enum):
    BOUTON = "bouton"
    TEXT = "text"
    FOLDER = "folder"

@dataclass
class User:
    user_id: int
    bot_id: int = 0
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_admin: bool = False
    is_banned: bool = False
    joined_date: datetime = field(default_factory=datetime.now)
    language: str = "fr"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) 

    @classmethod
    def from_dict(cls, data: dict):
        if "_id" in data:
            data.pop("_id")
        import inspect
        sig = inspect.signature(cls)
        filtered_data = {k: v for k, v in data.items() if k in sig.parameters}
        return cls(**filtered_data)

@dataclass
class Channel:
    channel_id: int
    title: str
    owner_id: int
    bot_id: int = 0
    username: Optional[str] = None
    link: Optional[str] = None
    members_count: int = 0
    ratio: float = 0.0
    about: str = ""
    photo: str = ""
    is_active: bool = True
    category: Optional[str] = None
    language: str = "fr"
    added_date: datetime = field(default_factory=datetime.now)
    added_by: Optional[int] = None
    failure_count: int = 0
    is_banned: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) 

    @classmethod
    def from_dict(cls, data: dict):
        if "_id" in data:
            data.pop("_id")
        # Filter out keys that don't belong to the dataclass
        import inspect
        sig = inspect.signature(cls)
        filtered_data = {k: v for k, v in data.items() if k in sig.parameters}
        return cls(**filtered_data)

@dataclass
class Adscross:
    creator_id: int
    content: str
    bot_id: int = 0
    name: Optional[str] = None
    status: AdStatus = AdStatus.PENDING
    target_channels: List[int] = field(default_factory=list)
    media_id: Optional[str] = None
    media_type: Optional[str] = None # photo, video, document, animation
    created_at: datetime = field(default_factory=datetime.now)
    ad_id: Optional[str] = None 
    ad_type: AdType = AdType.BOUTON
    folder_link: Optional[str] = None
    schedule_times: List[str] = field(default_factory=list) # ["08:00", "20:00"]
    schedule_days: List[int] = field(default_factory=list)  # [0, 1, 2, 3, 4, 5, 6]
    is_scheduled: bool = False
    last_sent_at: Optional[datetime] = None
    report_message_id: Optional[int] = None
    report_chat_id: Optional[int] = None
    reply_markup: Optional[dict] = None # Serialized InlineKeyboardMarkup

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self) 
        if data.get("ad_id") is None:
            data.pop("ad_id")
        return data

    @classmethod
    def from_dict(cls, data: dict):
        if "_id" in data:
            data["ad_id"] = str(data.pop("_id"))
        import inspect
        sig = inspect.signature(cls)
        filtered_data = {k: v for k, v in data.items() if k in sig.parameters}
        
        # Convert enums back from strings
        if "ad_type" in filtered_data and isinstance(filtered_data["ad_type"], str):
            filtered_data["ad_type"] = AdType(filtered_data["ad_type"])
        if "status" in filtered_data and isinstance(filtered_data["status"], str):
            filtered_data["status"] = AdStatus(filtered_data["status"])
            
        return cls(**filtered_data)
@dataclass
class SupportTicket:
    user_id: int
    bot_id: int = 0
    admin_id: Optional[int] = None
    status: str = "open" # open, active, closed
    created_at: datetime = field(default_factory=datetime.now)
    ticket_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if data.get("ticket_id") is None:
            data.pop("ticket_id")
        return data

    @classmethod
    def from_dict(cls, data: dict):
        if "_id" in data:
            data["ticket_id"] = str(data.pop("_id"))
        import inspect
        sig = inspect.signature(cls)
        filtered_data = {k: v for k, v in data.items() if k in sig.parameters}
        return cls(**filtered_data)

@dataclass
class SupportMessage:
    admin_id: int
    admin_message_id: int
    user_id: int
    ticket_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        if "_id" in data:
            data.pop("_id")
        return cls(**data)

@dataclass
class Post:
    ad_id: str
    channel_id: int
    message_id: int
    bot_id: int = 0
    sent_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "active"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        if "_id" in data:
            data.pop("_id")
        import inspect
        sig = inspect.signature(cls)
        filtered_data = {k: v for k, v in data.items() if k in sig.parameters}
        return cls(**filtered_data)

@dataclass
class AppStats:
    users_count: int = 0
    users_banned: int = 0
    Channel_count: int = 0
    Channel_banned: int = 0
    ads_count: int = 0
    ads_active: int = 0
    ads_completed: int = 0
    ads_canceled: int = 0
    posts_count: int = 0
    posts_in_channel: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        if "_id" in data:
            data.pop("_id")
        # Handle legacy typo from previous version
        if "users_cout" in data:
            data["users_count"] = data.pop("users_cout")
        # The original code had `return cls(**filtered_data)` but `filtered_data` was not defined here.
        # Assuming it should be `return cls(**data)` or `filtered_data` should be created.
        # For now, I'll assume the user wants to pass all data after handling the typo.
        # If `filtered_data` was intended, it would need to be created like in other from_dict methods.
        import inspect
        sig = inspect.signature(cls)
        filtered_data = {k: v for k, v in data.items() if k in sig.parameters}
        return cls(**filtered_data)

@dataclass
class CloneBot:
    user_id: int
    bot_token: str
    bot_id: int
    username: str
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        if "_id" in data:
            data.pop("_id")
        import inspect
        sig = inspect.signature(cls)
        filtered_data = {k: v for k, v in data.items() if k in sig.parameters}
        return cls(**filtered_data)

@dataclass
class PaidPromo:
    promo_id: str
    owner_id: int
    text: str
    url: str
    bot_id: int = 0
    name: Optional[str] = None
    is_active: bool = True
    added_date: datetime = field(default_factory=datetime.now)
    categories: List[str] = field(default_factory=list) # Targeted categories
    languages: List[str] = field(default_factory=list)  # Targeted languages

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        if "_id" in data:
            data.pop("_id")
        import inspect
        sig = inspect.signature(cls)
        filtered_data = {k: v for k, v in data.items() if k in sig.parameters}
        return cls(**filtered_data)

@dataclass
class AppSettings:
    bot_id: int = 0
    message_header: str = ""
    message_footer: str = ""
    button_prefix: str = "🔰"
    max_buttons_per_line: int = 5
    max_columns: int = 5
    max_rows: int = 10
    max_buttons: int = 50
    min_members: int = 1000
    max_members: int = 1000000
    delete_after_minutes: int = 30 # minutes
    auto_delete_ads: bool = True # auto delete ads after the specified time
    fuseau_horaire: str = "UTC"
    parse_mode: str = "html" # html, markdown, none
    folder_link: str = ""
    apps_stats: AppStats = field(default_factory=AppStats)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if isinstance(data.get("apps_stats"), AppStats):
             data["apps_stats"] = data["apps_stats"].to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict):
        if "_id" in data:
            data.pop("_id")
        if "apps_stats" in data and isinstance(data["apps_stats"], dict):
            data["apps_stats"] = AppStats.from_dict(data["apps_stats"])
            
        import inspect
        sig = inspect.signature(cls)
        filtered_data = {k: v for k, v in data.items() if k in sig.parameters}
        return cls(**filtered_data)