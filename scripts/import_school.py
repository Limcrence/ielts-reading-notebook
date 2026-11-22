"""Collect the signed-in student's graded IELTS reading exams and assignments."""

import argparse
import base64
from collections import defaultdict
from datetime import date
import hashlib
import json
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

from school_normalize import normalize


ROOT = Path(__file__).resolve().parent.parent
SITE = "https://tsinglantssa-stu.1course.cn"
SCHOOL = 12
FACULTY = 12
SUBJECT = 45
ROUTES = {
    "/api/user/listSchool", "/api/test/pageList", "/api/assignment/pageList",
    "/api/assignment/review/sub/listWithSection", "/api/test/review/reportCatalog/list",
    "/api/test/review/detail", "/api/test/review/report",
}


class ImportIssue(Exception):
    """An actionable error safe to show without dumping a school response."""


def say(message):
    print(message, flush=True)


def digest(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()[:24]


def save(path, data, verify=False, check_only=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, suffix=".json") as temp:
        pending = Path(temp.name)
    try:
        pending.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        if verify:
            result = subprocess.run([
                "node", "--disable-warning=ExperimentalWarning", "--experimental-strip-types",
                str(ROOT / "scripts/check-library.mjs"), str(pending),
            ], encoding="utf-8", capture_output=True)
            if result.returncode:
                raise ImportIssue("题库校验失败。" + result.stderr.strip())
        if not check_only:
            os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def batches(library, file_limit=15_000_000, question_limit=2000):
    """Keep each exercise with its entire passage and all its questions."""
    by_exercise = defaultdict(list)
    for row in library["questions"]:
        by_exercise[row["exercise_id"]].append(row)
    articles = {row["id"]: row for row in library["articles"]}

    def blank():
        return {"checked_at": library["checked_at"], "articles": [], "exercises": [], "questions": []}

    def size(row):
        return len(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) + 1

    batch = blank()
    used = size(batch)
    added = set()
    for exercise in library["exercises"]:
        article = articles[exercise["article_id"]]
        questions = by_exercise[exercise["id"]]
        exercise_size = size(exercise) + sum(size(q) for q in questions)
        article_size = size(article)
        increment = exercise_size + (0 if article["id"] in added else article_size)
        if batch["exercises"] and (used + increment > file_limit
                                   or len(batch["questions"]) + len(questions) > question_limit):
            yield batch
            batch, added = blank(), set()
            used, increment = size(batch), exercise_size + article_size
        if used + increment > file_limit or len(questions) > question_limit:
            raise ImportIssue(f'「{exercise["title"]}」单篇已超过网页导入上限，请检查题图大小。')
        if article["id"] not in added:
            added.add(article["id"])
            batch["articles"].append(article)
        batch["exercises"].append(exercise)
        batch["questions"].extend(questions)
        used += increment
    if batch["exercises"]:
        yield batch


def pages(request, route, filters, key):
    rows = []
    ids = set()
    page_index = 1
    total = None
    while True:
        page = request(route, {**filters, "pageIndex": page_index, "pageSize": 100})
        if total is None:
            total = page["total"]
        if page["total"] != total or page["page"] != page_index or not isinstance(page["list"], list):
            raise ImportIssue("学校列表在读取时发生变化，请重新运行。")
        for row in page["list"]:
            identity = (row["stuArchId"], row[key])
            if identity in ids:
                raise ImportIssue("学校列表重复返回同一条记录，请重新运行。")
            ids.add(identity)
            rows.append(row)
        if not page["next"]:
            if len(rows) != total:
                raise ImportIssue(f"学校列表只读到 {len(rows)}/{total} 条，请重新运行。")
            return rows
        if not page["list"] or page_index >= page["totalPages"]:
            raise ImportIssue("学校列表分页不完整，请重新运行。")
        page_index += 1


def discover(request, school, match):
    filters = {"facultyId": FACULTY, "schoolId": school, "subjectId": SUBJECT}
    exams = pages(request, "/api/test/pageList", filters, "testId")
    tasks = pages(request, "/api/assignment/pageList", filters, "assignmentId")
    archives = sorted({str(row["stuArchId"]) for row in exams + tasks})
    reports = {}

    def register(name, kind, test, archive, passages, revision, exam=False):
        if not passages:
            return
        key = digest([school, archive, test])
        selected = {p[0] for p in passages}
        if key in reports:
            previous = reports[key]
            original = previous["source"]
            original["selected_passages"] = sorted(selected.union(original["selected_passages"]))
            previous["revision"] = digest([previous["revision"], name, kind, revision, sorted(passages)])
            return
        reports[key] = {
            "source": {"source_type": kind, "name": name, "test_id": test,
                       "student_archive_id": archive, "exam_reviewed": exam,
                       "selected_passages": sorted(selected)},
            "revision": digest([2, name, kind, revision, sorted(passages)]),
        }

    for exam in exams:
        name = exam["testName"]
        if exam.get("reviewState") != "REVIEWED" or match.casefold() not in name.casefold():
            continue
        params = {"testId": exam["testId"], "stuArchId": exam["stuArchId"]}
        catalog = request("/api/test/review/reportCatalog/list", params)
        entries = [p for s in catalog for p in s["stuAnswerList"]]
        if not entries:
            raise ImportIssue(f"无法核对已批阅考试「{name}」的篇目。")
        passages = [(p["questionId"], p.get("questionVersion")) for p in entries
                    if p["type"].startswith("IELTS_READING")]
        register(name, "周测" if "周测" in name else "考试", exam["testId"], exam["stuArchId"],
                 passages, [exam.get("updateTime"), exam.get("score")], exam=True)

    for task in tasks:
        name = task["name"]
        records = request("/api/assignment/review/sub/listWithSection", {
            "facultyId": FACULTY, "assignmentId": task["assignmentId"], "stuArchId": task["stuArchId"],
        })
        for record in records:
            passages = []
            for section in record["sectionList"]:
                for p in section["questionList"]:
                    searchable = " ".join([name, section.get("sectionName", ""), p.get("name", "")])
                    if (p["type"].startswith("IELTS_READING") and p.get("state") == "ANSWERED"
                            and p.get("reviewState") == "REVIEWED" and match.casefold() in searchable.casefold()):
                        passages.append((p["id"], p.get("version"), p.get("score"), p.get("questionCount")))
            register(name, "真题汇总" if "真题" in name else "专项练习", record["testId"],
                     record["studentArchiveId"], passages, [task.get("updatedAt"), record.get("finishedAt")])
    return digest([SITE, school, archives]), reports


def read_report(request, source, load_image):
    test = source["test_id"]
    params = {"testId": test, "stuArchId": source["student_archive_id"]}
    detail = request("/api/test/review/detail", params)
    overview = request("/api/test/review/report", params) or {}
    if any(str(p["testId"]) != str(test) for s in detail for p in s["stuAnswers"]):
        raise ImportIssue("详情与列表中的报告不一致。")
    if any(overview.get(k) is not None and str(overview[k]) != str(v) for k, v in params.items()):
        raise ImportIssue("详情与列表中的报告不一致。")
    payloads = {"detail": {"data": detail}, "overview": {"data": overview}}
    library, checks = normalize([source], date.today().isoformat(), lambda _, kind: payloads[kind])
    expected = {f"{test}-{p}" for p in source["selected_passages"]}
    if ({row["exercise_id"] for row in checks} != expected or len(checks) != len(expected)
            or not all(row["points_match"] and row["score_match"] for row in checks)):
        raise ImportIssue("篇目数量或分数与学校报告不一致。")
    warnings = []
    for article in library["articles"]:
        article.pop("image_urls", None)
    for question in library["questions"]:
        images = []
        for url in question.get("image_urls", []):
            image = load_image(url)
            if image:
                images.append(image)
            else:
                warnings.append(f'{question["passage_code"]} 第 {question["question_number"]} 题图示待补')
        question["image_urls"] = images
    return library, warnings


def collect(request, school, base, load_image, match=""):
    owner, reports = discover(request, school, match)
    if not reports:
        say("目录已核对。符合范围的已批阅阅读报告为 0 份。")
        return 0
    folder = base / owner
    run = folder / ("all" if not match else digest(match.casefold()))
    status = {k: {"name": r["source"]["name"], "state": "待处理"} for k, r in reports.items()}
    progress_file = run / "progress.json"
    def checkpoint():
        save(progress_file, {"total": len(status), "reports": status})
    checkpoint()
    say(f"找到 {len(reports)} 份已批阅的阅读报告。")
    say(f"本次清单：{progress_file}")
    merged = {kind: {} for kind in ("articles", "exercises", "questions")}
    ready = 0
    issues = (ImportIssue, KeyError, TypeError, ValueError, OSError, AttributeError, IndexError)
    for key, report in reports.items():
        name = report["source"]["name"]
        part = folder / "reports" / key / (report["revision"] + ".json")
        try:
            try:
                cached = json.loads(part.read_text(encoding="utf-8"))
                library, warnings = cached["library"], cached["warnings"]
                if cached["checksum"] != digest([library, warnings]):
                    raise ValueError("cache checksum")
            except (FileNotFoundError, KeyError, TypeError, ValueError):
                library, warnings = read_report(request, report["source"], load_image)
                for batch in batches(library):
                    save(part, batch, verify=True, check_only=True)
                # Retry missing diagrams on the next run; otherwise reuse the verified report.
                if not warnings:
                    save(part, {"library": library, "warnings": warnings, "checksum": digest([library, warnings])})
            for kind in merged:
                for row in library[kind]:
                    existing = merged[kind].get(row["id"])
                    if existing is not None and (kind != "articles" or existing != row):
                        raise ImportIssue("不同报告使用了相同编号，请核对原卷。")
                    merged[kind][row["id"]] = row
            status[key].update(state="已读取", exercises=len(library["exercises"]), warnings=warnings)
            ready += 1
        except issues as error:
            status[key].update(state="未读取", error=str(error))
        checkpoint()
        say(f'{status[key]["state"]} · {name} · 已读取 {ready}/{len(status)}')
        if "error" in status[key]:
            say("  " + status[key]["error"])
    if ready != len(reports):
        say("批量未完成。重新运行同一命令可继续，正式题库保留上一份。")
        return 2
    library = {kind: list(rows.values()) for kind, rows in merged.items()}
    library["checked_at"] = date.today().isoformat()
    files = list(batches(library))
    outputs = []
    if len(files) > 1:
        destination = run / ("export-" + digest(library))
    for i, batch in enumerate(files, 1):
        output = (run / "school-library.json" if len(files) == 1
                  else destination / f"school-library-{i:02d}.json")
        save(output, batch, verify=True)
        outputs.append(output)
    warnings = sum(len(row["warnings"]) for row in status.values())
    say(f'已导出 {ready}/{len(status)} 份报告，{len(library["exercises"])} 篇练习，'
        f'{len(library["questions"])} 个题组。图示待补 {warnings} 项。')
    for output in outputs:
        say(f"题库文件：{output}")
    return 0


def run_browser(match):
    from playwright.sync_api import Error as BrowserError, sync_playwright

    with sync_playwright() as engine:
        channels = ["msedge", None, "chrome"] if sys.platform == "win32" else [None, "chrome"]
        for channel in channels:
            try:
                browser = engine.chromium.launch(channel=channel, headless=False)
                break
            except BrowserError:
                continue
        else:
            raise ImportIssue("浏览器启动失败，请运行 python -m playwright install chromium 后重试。")
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto(SITE + "/home", wait_until="domcontentloaded", timeout=60000)
        except BrowserError:
            raise ImportIssue("无法打开学校官网，请检查网络后重新运行。") from None

        def request(route, payload=None):
            if route not in ROUTES:
                raise ImportIssue("不支持的学校报告网址。")
            try:
                result = page.evaluate("""async ({site, route, payload}) => {
                    if (location.origin !== site) return {status: 0};
                    const response = await fetch(route, {
                        method: payload === null ? 'GET' : 'POST',
                        headers: {'Accept': 'application/json', 'Content-Type':'application/json'},
                        body: payload === null ? undefined : JSON.stringify(payload),
                        credentials: 'same-origin', redirect: 'error', cache: 'no-store',
                        signal: AbortSignal.timeout(30000),
                    });
                    if (!response.ok) return {status: response.status};
                    const body = await response.json();
                    return {status: response.status, code: body.errorCode ?? 0, data: body.data};
                }""", {"site": SITE, "route": route, "payload": payload})
                if not 200 <= result["status"] < 300:
                    raise ImportIssue(f'学校页面请求未成功（{result["status"]}），请检查登录和网络。')
                if (result["code"] != 0 or "data" not in result
                        or (result["data"] is None and route != "/api/test/review/report")):
                    raise ImportIssue("学校未返回报告数据，请检查登录或报告权限。")
                return result["data"]
            except (BrowserError, ValueError):
                raise ImportIssue("学校请求失败，请检查网络并重新运行。") from None

        say("请在新打开的学校官网窗口登录。登录成功后会自动开始。")
        deadline = time.monotonic() + 600
        schools = None
        while time.monotonic() < deadline and not page.is_closed():
            try:
                schools = request("/api/user/listSchool")
                if isinstance(schools, list) and schools:
                    break
            except ImportIssue:
                pass
            page.wait_for_timeout(2500)
        if not schools or page.is_closed():
            raise ImportIssue("未检测到学校登录，请重新运行。")
        # The student site can return several schools. Restrict this importer to the configured school.
        school_ids = [s.get("id") or s.get("schoolId") for s in schools]
        if len(school_ids) == 1 and school_ids[0]:
            school = school_ids[0]
        elif SCHOOL in school_ids:
            school = SCHOOL
        else:
            raise ImportIssue("无法确定本次登录的学校。")

        assets = engine.request.new_context()
        images = {}
        def load_image(url):
            if url in images:
                return images[url]
            parsed = urlsplit(url)
            if parsed.scheme != "https" or parsed.netloc != "lms-cdn.schoolis.cn":
                return None
            response = None
            try:
                response = assets.get(url, max_redirects=0, timeout=15000)
                if not response.ok:
                    return None
                data = response.body()
                mime = None
                if data.startswith(b"\x89PNG\r\n\x1a\n"):
                    mime = "png"
                elif data.startswith(b"\xff\xd8\xff"):
                    mime = "jpeg"
                elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
                    mime = "webp"
                if mime and len(data) <= 5_900_000:
                    images[url] = f"data:image/{mime};base64," + base64.b64encode(data).decode("ascii")
                return images.get(url)
            except BrowserError:
                return None
            finally:
                if response is not None:
                    response.dispose()
        try:
            return collect(request, school, ROOT / ".private/school-import", load_image, match)
        finally:
            assets.dispose()
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--match", default="", help="只读取名称匹配的考试、作业或专项；默认全部")
    args = parser.parse_args()
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(errors="replace")
        if not shutil.which("node"):
            raise ImportIssue("需要安装模板 package.json 支持的 Node.js 版本。")
        sys.exit(run_browser(args.match.strip()))
    except ModuleNotFoundError as error:
        parser.exit(1, f"缺少 {error.name}，请在当前 Python 环境安装 playwright。\n")
    except KeyboardInterrupt:
        parser.exit(2, "已中断，重新运行可继续。\n")
    except (ImportIssue, KeyError, TypeError, ValueError, OSError) as error:
        parser.exit(2, f"批量未完成。{error}\n")
