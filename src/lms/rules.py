from dataclasses import dataclass

from .models import ReaderType


@dataclass(frozen=True)
class BorrowRule:
    max_books: int
    loan_days: int
    renew_times: int
    renew_days: int
    max_reservations: int
    overdue_grace_days: int = 7


DEFAULT_RULES = {
    ReaderType.UNDERGRAD: BorrowRule(max_books=5, loan_days=30, renew_times=1, renew_days=15, max_reservations=2),
    ReaderType.GRADUATE: BorrowRule(max_books=10, loan_days=60, renew_times=2, renew_days=30, max_reservations=3),
    ReaderType.TEACHER: BorrowRule(max_books=15, loan_days=90, renew_times=2, renew_days=30, max_reservations=5),
}
