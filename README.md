# 雅思阅读错题本

把你做过的雅思阅读整理成自己的错题本。你可以重做错题、对照原文看解析，也可以按「今日」里的计划复习。电脑上用 WorkBuddy 帮你准备，平时在浏览器里刷题。

## 第一次用，照这三步来

1. [下载错题本模板 ZIP](https://github.com/Limcrence/ielts-reading-notebook/archive/refs/heads/main.zip)，解压到自己的电脑。Windows 可以右键选「全部解压缩」，Mac 双击 ZIP 即可。直接下载，无需 GitHub 账号。
2. 打开 [WorkBuddy 桌面版](https://www.workbuddy.cn/)，新建任务，把「工作目录」选成刚解压的文件夹。选对的标志是打开这个文件夹能直接看到 `README.md` 和 `WORKBUDDY_PROMPT.md`。
3. 复制下面这句话，发给 WorkBuddy。

```text
请读取当前文件夹里的 WORKBUDDY_PROMPT.md，照里面的要求帮我把雅思阅读错题本跑起来。先试一题示例，再带我导入自己的第一篇已批阅阅读。能做的请你直接做。轮到我操作时，用中文告诉我现在点哪里、看到什么算成功。
```

先看示例。WorkBuddy 给你网址后，用电脑上的普通浏览器打开，点「试用示例题库」。等示例能打开，再准备一篇自己的已批阅阅读。已有 PDF、网页存档或清晰截图就用已有文件。学校报告在网页上时，由你自己在学校官网登录。WorkBuddy 会告诉你具体要打开哪一页，或把哪个文件放到哪里。

## 以后怎么用

| 你想做什么 | 怎么做 |
| --- | --- |
| 继续刷题 | 用同一台电脑、同一个浏览器打开原来的网址，点「继续我的复习」。如果网页打不开，把「帮我重新打开错题本，用原来的网址和进度」发给 WorkBuddy。 |
| 加一份新周测 | 打开原来的 WorkBuddy 任务，发「帮我把这次已批阅的周测加进去，保留以前的题和进度」。按它的指引导入更新后的题库。 |
| 留一份备份 | 在做题页右上角点「⋯」→「导出备份」，另外保留 WorkBuddy 生成的题库文件。恢复时先导入题库，再用「⋯」→「导入备份」恢复复习进度。 |

题库和复习进度保存在本机。学校报告和自己的题库留在本地 `.private/` 文件夹，进度备份也保存在自己能找到的位置。这里公开的是应用、原创示例和操作提示词。

## 手动运行

如果你习惯用终端，可以在模板文件夹运行以下命令。Node.js 版本以 [package.json](./package.json) 为准。

```sh
npm ci
npm run check:library
npm run dev
```

启动后打开 `http://127.0.0.1:5173/`。个人题库用 `npm run check:library -- .private/reading-library.json` 检查，应用用 `npm run build` 检查构建。题库格式见 [示例](./examples/reading-library.json) 和 [校验规则](./src/lib/library-import.ts)。

## 许可证

应用代码和原创示例采用 [MIT 许可证](./LICENSE)。React、Vite、Lucide 和 ts-fsrs 各自遵循其许可证。
