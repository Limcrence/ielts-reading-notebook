# 给本机 AI 的导入指令

请在学生自己的电脑上，把清澜山学校已批阅的雅思阅读考试和作业导入错题本，包括周测、专项和真题汇总。

1. 下载[最新版模板](https://github.com/Limcrence/ielts-reading-notebook/archive/refs/heads/main.zip)，在含 `package.json` 的目录工作。已有错题本就沿用原目录、网址和浏览器，更新程序时保留 `.private/`。需要符合 `package.json` 的 Node.js、Python 3.9+ 和 Playwright。缺少 Playwright 时执行 `python -m pip install playwright`。系统使用 `python3` 或 `py` 时，请始终用同一个解释器。
2. **运行 `python -u scripts/import_school.py` 并持续等待。** 学生在弹出的学校官网亲自登录，程序自动读取。若提示缺少浏览器，执行 `python -m playwright install chromium` 后重试。默认全部；仅当学生指定范围时加 `--match "关键词"`。
3. 按程序的总数跟到结束。显示“已读取 1/12”时继续。中断就重跑同一命令，复用已校验的报告。退出码非零时处理报错再重试；确实受阻就报出剩余报告和原因。零份也如实告知。
4. 用 `npm ci`、`npm run dev` 启动网页。在原浏览器点「导入我的题库」，依次选择本次成功输出的全部文件。已有旧版 AI 手工编号的题库时，先按来源、篇名、题号对齐旧编号，再合并，以保留已有作答进度。
5. 给答错和部分正确的题补解析，写清原文段落、证据句、同义替换和理由。证据不足的列为待补。沿用原编号和已有解析，另存补写版，用 `npm run check:library -- "文件完整路径"` 校验，再导入。对照清单核实每份报告，抽查一题的原作答和标准答案。最后告诉学生**报告共几份、网页已导入几份、还缺什么**。只导出了文件就标明网页尚未导入。

学校登录仅在官网窗口操作。个人题库、缓存和进度清单留在当前电脑的 `.private/`。
