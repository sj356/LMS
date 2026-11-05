from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class ReaderType(str, Enum):
    UNDERGRAD = "本科生"
    GRADUATE = "研究生"
    TEACHER = "教师"


class ReaderStatus(str, Enum):
    NORMAL = "正常"
    LOST = "挂失"
    FROZEN = "冻结"
    CANCELLED = "注销"


class CopyStatus(str, Enum):
    AVAILABLE = "在架"
    BORROWED = "已借出"
    RESERVED = "预约保留"
    REPAIRING = "维修中"
    DISCARDED = "已注销"


@dataclass
class Reader:
    reader_id: str
    name: str
    reader_type: ReaderType
    status: ReaderStatus = ReaderStatus.NORMAL
    frozen_reason: str = ""


@dataclass
class BookCopy:
    barcode: str
    title: str
    isbn: str = ""
    status: CopyStatus = CopyStatus.AVAILABLE
    location: str = ""


@dataclass
class Loan:
    loan_id: str
    reader_id: str
    barcode: str
    borrow_date: date
    due_date: date
    return_date: date | None = None

    @property
    def is_returned(self) -> bool:
        return self.return_date is not None

    def is_overdue(self, today: date) -> bool:
        return not self.is_returned and self.due_date < today

    def overdue_days(self, today: date) -> int:
        if not self.is_overdue(today):
            return 0
        return (today - self.due_date).days


@dataclass
class EligibilityResult:
    ok: bool
    code: str = "OK"
    message: str = ""
    details: dict = field(default_factory=dict)
