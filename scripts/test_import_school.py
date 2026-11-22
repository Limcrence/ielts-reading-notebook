import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from import_school import batches, collect, ImportIssue, pages


def page(rows, number=1, total=None, more=False):
    return {"list": rows, "page": number, "total": len(rows) if total is None else total,
            "next": more, "totalPages": 2 if more else number}


def doc(*lines):
    return {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": line}]} for line in lines]}


class School:
    def __init__(self):
        self.archive = 1
        self.broken = set()
        self.read = []
        self.missing_passage = False
        self.revision = 1

    def request(self, route, params):
        if route == "/api/test/pageList":
            index = params["pageIndex"]
            return page([{"testId": index, "stuArchId": self.archive, "reviewState": "REVIEWED",
                          "testName": f"周测 {index}", "updateTime": self.revision if index == 2 else 1}],
                        index, 2, index == 1)
        if route == "/api/assignment/pageList":
            return page([{"assignmentId": 3, "stuArchId": self.archive, "name": "课程作业"}])
        if "listWithSection" in route:
            passages = [
                {"id": n, "type": typ, "state": "ANSWERED", "reviewState": grade, "name": "专项"}
                for n, typ, grade in [(31, "IELTS_READING_P3", "REVIEWED"),
                                      (32, "IELTS_READING_P2", "UN_REVIEWED"),
                                      (33, "IELTS_LISTENING", "REVIEWED")]]
            return [{"testId": 3, "studentArchiveId": self.archive,
                     "sectionList": [{"sectionName": "阅读", "questionList": passages}]}]
        test = params["testId"]
        ids = {1: [11, 12], 2: [21], 3: [31]}[test]
        if "reportCatalog" in route:
            return [{"stuAnswerList": [{"questionId": n, "type": "IELTS_READING_P1"} for n in ids]}]
        if route.endswith("/report"):
            return None
        if route.endswith("/detail"):
            self.read.append(test)
            if test in self.broken:
                raise ImportIssue("模拟断线")
            if self.missing_passage and test == 1:
                ids = ids[:1]
            result = []
            for n in ids:
                question = {"questionId": n * 10, "type": "TEXT_GAP", "questionCount": 1,
                            "questionBody": {"title": doc("Which colour?")},
                            "referenceAnswer": {"answers": {"answer": ["blue"]}},
                            "answer": {"answers": {"answer": ["red"]}}, "score": 0}
                result.append({"testId": test, "questionId": n, "questionName": f"P{n}",
                               "state": "ANSWERED", "reviewState": "REVIEWED", "score": 0, "totalScore": 1,
                               "questionBody": {"title": doc(f"River {n}", f"The water at pier {n} was blue.")},
                               "childNodeList": [question]})
            return [{"stuAnswers": result}]
        raise AssertionError(route)


class ImportChecks(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.school = School()

    def collect(self, match=""):
        with contextlib.redirect_stdout(io.StringIO()) as log:
            code = collect(self.school.request, 12, self.base, lambda _: None, match)
        return code, log.getvalue()

    def test_partial_resume_refresh_and_account_isolation(self):
        self.school.broken = {2, 3}
        code, log = self.collect()
        self.assertEqual(code, 2)
        self.assertIn("已读取 1/3", log)
        self.assertFalse(list(self.base.rglob("school-library.json")))
        state = json.loads(next(self.base.rglob("progress.json")).read_text(encoding="utf-8"))
        self.assertEqual(sum(r["state"] == "未读取" for r in state["reports"].values()), 2)
        self.school.broken.clear()
        self.school.read.clear()
        code, log = self.collect()
        self.assertEqual(code, 0)
        self.assertEqual(self.school.read, [2, 3])
        self.assertIn("3/3 份报告，4 篇练习", log)
        output = next(self.base.rglob("school-library.json"))
        old = output.read_bytes()
        self.school.revision += 1
        self.school.broken.add(2)
        self.assertEqual(self.collect()[0], 2)
        self.assertEqual(output.read_bytes(), old)
        self.school.broken.clear()
        self.school.archive = 2
        self.school.read.clear()
        self.assertEqual(self.collect()[0], 0)
        self.assertEqual(self.school.read, [1, 2, 3])
        self.assertEqual(len(list(self.base.rglob("school-library.json"))), 2)

    def test_one_missing_passage_in_a_graded_report(self):
        self.school.missing_passage = True
        code, log = self.collect("周测 1")
        self.assertEqual(code, 2)
        self.assertIn("已读取 0/1", log)

    def test_incomplete_pagination_and_empty_scope(self):
        def truncated(_, payload):
            return page([{"stuArchId": 1, "testId": 1}], total=5)
        with self.assertRaisesRegex(ImportIssue, "1/5"):
            pages(truncated, "", {}, "testId")
        code, log = self.collect("unassigned")
        self.assertEqual(code, 0)
        self.assertIn("0 份", log)
        self.assertFalse(list(self.base.rglob("school-library.json")))

    def test_split_preserves_passages_and_questions(self):
        self.assertEqual(self.collect()[0], 0)
        library = json.loads(next(self.base.rglob("school-library.json")).read_text(encoding="utf-8"))
        files = list(batches(library, question_limit=2))
        self.assertEqual([len(f["questions"]) for f in files], [2, 2])
        for f in files:
            self.assertEqual({q["exercise_id"] for q in f["questions"]}, {e["id"] for e in f["exercises"]})
            self.assertEqual({q["article_id"] for q in f["questions"]}, {a["id"] for a in f["articles"]})
        with self.assertRaisesRegex(ImportIssue, "单篇"):
            list(batches(library, file_limit=128))


if __name__ == "__main__":
    unittest.main()
