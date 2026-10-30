from datetime import date

from .models import BookCopy, CopyStatus, Loan, Reader


class LibraryRepository:
    def __init__(self):
        self._readers: dict[str, Reader] = {}
        self._copies: dict[str, BookCopy] = {}
        self._loans: list[Loan] = []
        self._logs: list[dict] = []
        self._seq = 0

    def add_reader(self, reader: Reader) -> Reader:
        self._readers[reader.reader_id] = reader
        return reader

    def add_copy(self, copy: BookCopy) -> BookCopy:
        self._copies[copy.barcode] = copy
        return copy

    def get_reader(self, reader_id: str) -> Reader | None:
        return self._readers.get(reader_id)

    def get_copy(self, barcode: str) -> BookCopy | None:
        return self._copies.get(barcode)

    def loans_of(self, reader_id: str) -> list[Loan]:
        return [x for x in self._loans if x.reader_id == reader_id]

    def active_loans_of(self, reader_id: str) -> list[Loan]:
        return [x for x in self._loans if x.reader_id == reader_id and not x.is_returned]

    def overdue_loans_of(self, reader_id: str, today: date) -> list[Loan]:
        return [x for x in self.active_loans_of(reader_id) if x.is_overdue(today)]

    def available_copies(self) -> list[BookCopy]:
        return [x for x in self._copies.values() if x.status is CopyStatus.AVAILABLE]

    def next_loan_id(self) -> str:
        self._seq += 1
        return f"LN-{self._seq:06d}"

    def save_loan(self, loan: Loan) -> Loan:
        self._loans.append(loan)
        return loan

    def all_loans(self) -> list[Loan]:
        return list(self._loans)

    def add_log(self, entry: dict) -> None:
        self._logs.append(entry)

    def logs(self) -> list[dict]:
        return list(self._logs)
