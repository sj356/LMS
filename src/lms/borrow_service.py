from dataclasses import dataclass, field
from datetime import date, timedelta

from .models import CopyStatus, EligibilityResult, Loan, Reader, ReaderStatus
from .repository import LibraryRepository
from .rules import DEFAULT_RULES, BorrowRule


@dataclass
class BorrowOutcome:
    reader: Reader | None = None
    loans: list[Loan] = field(default_factory=list)
    rejections: list[tuple[str, EligibilityResult]] = field(default_factory=list)

    @property
    def receipt(self) -> str:
        if not self.loans:
            return ""
        lines = ["借阅凭条"]
        if self.reader is not None:
            lines.append(f"读者：{self.reader.name}（{self.reader.reader_id}，{self.reader.reader_type.value}）")
        lines.append(f"借出册数：{len(self.loans)} 册")
        for loan in self.loans:
            lines.append(f"  《{loan.title}》 {loan.barcode}  应还日期 {loan.due_date.isoformat()}")
        lines.append(f"借阅日期：{self.loans[0].borrow_date.isoformat()}")
        return "\n".join(lines)


class BorrowService:
    def __init__(self, repo: LibraryRepository, rules: dict | None = None, today: date | None = None):
        self.repo = repo
        self.rules = rules or DEFAULT_RULES
        self.today = today or date.today()

    def rule_of(self, reader: Reader) -> BorrowRule:
        return self.rules[reader.reader_type]

    def check(self, reader_id: str, barcode: str, extra_borrowed: int = 0) -> EligibilityResult:
        reader = self.repo.get_reader(reader_id)
        if reader is None:
            return EligibilityResult(False, "READER_NOT_FOUND", f"读者证号 {reader_id} 不存在，请核对后重新扫描。")

        if reader.status is ReaderStatus.CANCELLED:
            return EligibilityResult(False, "CARD_CANCELLED", "读者证已注销，不能借书；请到办证处重新办理。")
        if reader.status is ReaderStatus.LOST:
            return EligibilityResult(False, "CARD_LOST", "读者证处于挂失状态，不能借书；请先解挂或补办后再借。")
        if reader.status is ReaderStatus.FROZEN:
            reason = reader.frozen_reason or "未注明原因"
            return EligibilityResult(False, "READER_FROZEN", f"读者证已冻结（{reason}），请先处理后再借。")

        rule = self.rule_of(reader)
        active = self.repo.active_loans_of(reader_id)
        held = len(active) + extra_borrowed
        if held >= rule.max_books:
            return EligibilityResult(
                False,
                "OVER_LIMIT",
                f"{reader.reader_type.value}借阅上限 {rule.max_books} 册，当前已借 {len(active)} 册，"
                f"还可借 {max(rule.max_books - held, 0)} 册；请先归还图书后再借。",
                {"limit": rule.max_books, "current": len(active), "requested": extra_borrowed + 1},
            )

        overdue = self.repo.overdue_loans_of(reader_id, self.today)
        if overdue:
            longest = max(x.overdue_days(self.today) for x in overdue)
            return EligibilityResult(
                False,
                "HAS_OVERDUE",
                f"当前有 {len(overdue)} 册图书超期未还（最长超期 {longest} 天），请先归还后再借。",
                {"overdue_count": len(overdue), "max_days": longest},
            )

        copy = self.repo.get_copy(barcode)
        if copy is None:
            return EligibilityResult(False, "COPY_NOT_FOUND", f"条码 {barcode} 不存在，请确认条码或到馆员处查询。")
        if copy.status is CopyStatus.BORROWED:
            return EligibilityResult(False, "COPY_BORROWED", f"《{copy.title}》（{barcode}）已借出，可预约其他复本。")
        if copy.status is CopyStatus.RESERVED:
            return EligibilityResult(False, "COPY_RESERVED", f"《{copy.title}》（{barcode}）为预约保留复本，暂不可借。")
        if copy.status is CopyStatus.REPAIRING:
            return EligibilityResult(False, "COPY_REPAIRING", f"《{copy.title}》（{barcode}）维修中，暂不可借。")
        if copy.status is CopyStatus.DISCARDED:
            return EligibilityResult(False, "COPY_DISCARDED", f"《{copy.title}》（{barcode}）已注销，不可借阅。")

        return EligibilityResult(
            True,
            "OK",
            f"校验通过，可借 {max(rule.max_books - held - 1, 0)} 册，应于 "
            f"{(self.today + timedelta(days=rule.loan_days)).isoformat()} 前归还。",
            {"rule": rule, "current": len(active)},
        )

    def borrow(self, reader_id: str, barcodes: list[str]) -> BorrowOutcome:
        outcome = BorrowOutcome(reader=self.repo.get_reader(reader_id))
        if not barcodes:
            return outcome

        staged: list[str] = []
        for barcode in barcodes:
            if barcode in staged:
                result = EligibilityResult(False, "DUPLICATE_SCAN", f"条码 {barcode} 在本次借阅中重复扫描，请核对。")
            else:
                result = self.check(reader_id, barcode, extra_borrowed=len(staged))
            if not result.ok:
                self._log(reader_id, barcode, result)
                outcome.rejections.append((barcode, result))
                return outcome
            staged.append(barcode)

        rule = self.rule_of(outcome.reader)
        for barcode in staged:
            copy = self.repo.get_copy(barcode)
            loan = Loan(
                loan_id=self.repo.next_loan_id(),
                reader_id=reader_id,
                barcode=barcode,
                borrow_date=self.today,
                due_date=self.today + timedelta(days=rule.loan_days),
                title=copy.title,
            )
            self.repo.save_loan(loan)
            copy.status = CopyStatus.BORROWED
            outcome.loans.append(loan)
        return outcome

    def _log(self, reader_id: str, barcode: str, result: EligibilityResult) -> None:
        self.repo.add_log(
            {
                "at": self.today.isoformat(),
                "reader_id": reader_id,
                "barcode": barcode,
                "code": result.code,
                "message": result.message,
            }
        )
