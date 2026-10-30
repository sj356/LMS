import unittest
from datetime import date

from src.lms import (
    BorrowService,
    BookCopy,
    CopyStatus,
    LibraryRepository,
    Reader,
    ReaderStatus,
    ReaderType,
)


class BorrowServiceTest(unittest.TestCase):
    TODAY = date(2026, 11, 10)

    def setUp(self):
        self.repo = LibraryRepository()
        self.repo.add_reader(Reader("R2001", "李同学", ReaderType.UNDERGRAD))
        self.repo.add_reader(Reader("R3001", "王老师", ReaderType.TEACHER))
        self.repo.add_reader(Reader("R4001", "张同学", ReaderType.GRADUATE))
        for i in range(1, 21):
            self.repo.add_copy(BookCopy(f"B{i:04d}", f"软件工程（第{i}版）"))
        self.service = BorrowService(self.repo, today=self.TODAY)

    def borrow_ok(self, reader_id, barcodes):
        outcome = self.service.borrow(reader_id, barcodes)
        self.assertEqual(outcome.rejections, [])
        self.assertEqual(len(outcome.loans), len(barcodes))
        return outcome

    def test_tc01_undergrad_borrow_sets_due_date_and_receipt(self):
        outcome = self.borrow_ok("R2001", ["B0001"])
        loan = outcome.loans[0]
        self.assertEqual(loan.due_date, date(2026, 12, 10))
        self.assertEqual(self.repo.get_copy("B0001").status, CopyStatus.BORROWED)
        for expected in ("李同学", "软件工程（第1版）", "B0001", "2026-11-10", "2026-12-10"):
            self.assertIn(expected, outcome.receipt)

    def test_tc02_batch_scan_registers_all_copies(self):
        outcome = self.borrow_ok("R2001", ["B0001", "B0002", "B0003"])
        self.assertEqual({x.barcode for x in outcome.loans}, {"B0001", "B0002", "B0003"})
        self.assertEqual(len(self.repo.active_loans_of("R2001")), 3)

    def test_tc03_limit_reached_rejects_with_numbers(self):
        self.borrow_ok("R2001", ["B0001", "B0002", "B0003", "B0004", "B0005"])
        result = self.service.check("R2001", "B0006")
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "OVER_LIMIT")
        self.assertIn("上限 5 册", result.message)
        self.assertIn("当前已借 5 册", result.message)
        self.assertIn("还可借 0 册", result.message)

    def test_tc04_returned_copies_free_the_quota(self):
        outcome = self.borrow_ok("R2001", ["B0001", "B0002", "B0003", "B0004", "B0005"])
        outcome.loans[0].return_date = self.TODAY
        self.repo.get_copy("B0001").status = CopyStatus.AVAILABLE
        result = self.service.check("R2001", "B0006")
        self.assertTrue(result.ok, result.message)

    def test_tc05_overdue_loan_blocks_borrowing(self):
        outcome = self.borrow_ok("R2001", ["B0001"])
        outcome.loans[0].due_date = date(2026, 10, 31)
        result = self.service.check("R2001", "B0002")
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "HAS_OVERDUE")
        self.assertIn("1 册图书超期", result.message)
        self.assertIn("10 天", result.message)

    def test_tc06_lost_card_rejected(self):
        self.repo.get_reader("R2001").status = ReaderStatus.LOST
        result = self.service.check("R2001", "B0001")
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "CARD_LOST")

    def test_tc07_frozen_reader_rejected_with_reason(self):
        reader = self.repo.get_reader("R2001")
        reader.status = ReaderStatus.FROZEN
        reader.frozen_reason = "罚款未缴"
        result = self.service.check("R2001", "B0001")
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "READER_FROZEN")
        self.assertIn("罚款未缴", result.message)

    def test_tc08_reserved_copy_rejected(self):
        self.repo.get_copy("B0002").status = CopyStatus.RESERVED
        result = self.service.check("R2001", "B0002")
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "COPY_RESERVED")

    def test_tc09_unknown_barcode_rejected(self):
        result = self.service.check("R2001", "X9999")
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "COPY_NOT_FOUND")
        self.assertIn("X9999", result.message)

    def test_tc10_teacher_loan_days_90(self):
        outcome = self.borrow_ok("R3001", ["B0001"])
        self.assertEqual(outcome.loans[0].due_date, date(2027, 2, 8))

    def test_tc11_graduate_limit_10(self):
        self.borrow_ok("R4001", [f"B{i:04d}" for i in range(1, 11)])
        result = self.service.check("R4001", "B0011")
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "OVER_LIMIT")
        self.assertIn("上限 10 册", result.message)

    def test_tc12_batch_with_one_unavailable_copy_is_rolled_back(self):
        self.repo.get_copy("B0002").status = CopyStatus.REPAIRING
        outcome = self.service.borrow("R2001", ["B0001", "B0002", "B0003"])
        self.assertEqual(outcome.loans, [])
        self.assertEqual(len(outcome.rejections), 1)
        self.assertEqual(outcome.rejections[0][1].code, "COPY_REPAIRING")
        self.assertEqual(self.repo.active_loans_of("R2001"), [])
        self.assertEqual(self.repo.get_copy("B0001").status, CopyStatus.AVAILABLE)
        self.assertEqual(self.repo.get_copy("B0003").status, CopyStatus.AVAILABLE)

    def test_tc13_unknown_reader_rejected(self):
        result = self.service.check("R9999", "B0001")
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "READER_NOT_FOUND")

    def test_tc14_rejection_is_written_to_operation_log(self):
        self.repo.get_copy("B0002").status = CopyStatus.RESERVED
        self.service.borrow("R2001", ["B0002"])
        logs = self.repo.logs()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["reader_id"], "R2001")
        self.assertEqual(logs[0]["code"], "COPY_RESERVED")

    def test_tc15_limit_takes_precedence_over_overdue(self):
        outcome = self.borrow_ok("R2001", ["B0001", "B0002", "B0003", "B0004", "B0005"])
        outcome.loans[0].due_date = date(2026, 10, 31)
        result = self.service.check("R2001", "B0006")
        self.assertFalse(result.ok)
        self.assertEqual(result.code, "OVER_LIMIT")

    def test_tc16_batch_quota_is_checked_cumulatively(self):
        self.borrow_ok("R2001", ["B0001", "B0002", "B0003", "B0004"])
        outcome = self.service.borrow("R2001", ["B0005", "B0006", "B0007"])
        self.assertEqual(outcome.loans, [])
        self.assertEqual(len(self.repo.active_loans_of("R2001")), 4)
        self.assertEqual(self.repo.get_copy("B0005").status, CopyStatus.AVAILABLE)


if __name__ == "__main__":
    unittest.main()
