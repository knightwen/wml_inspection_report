# WML Inspection Report Workbench

本地检查报告工作台，当前版本 **0.1.1**。支持拖入多张现场照片、选择并编辑 Observation / Recommendation、保存检查项，并按 Word 模板生成 DOCX 报告。

## 使用

从 [GitHub Releases](https://github.com/knightwen/wml_inspection_report/releases/latest) 下载 `InspectionWorkbench_v版本号_Windows_x64.zip`。请下载发布附件中的便携 ZIP；GitHub 自动生成的 `Source code (zip)` 只有源码。首次发布完成后此入口才会有下载包。

Windows 10/11 64 位便携程序：解压完整分发包，双击 `InspectionWorkbench.exe`，在自动打开的本地浏览器中操作。无需安装 Python、Word 或照片编解码器；查看和继续编辑 DOCX 可使用 Word。

1. 填写报告信息和封面信息。
2. 拖入 JPG、PNG、WEBP、HEIC 或 HEIF；一个检查项可包含多张照片，可旋转和调整顺序。
3. 填写 Element、Condition Rating、Likelihood、Severity 和 Priority。菜单允许手动编辑。
4. 搜索并选择 Observation / Recommendation，再按现场情况编辑。
5. 点击 Save，将检查项保存到列表；支持重新编辑、删除和调整顺序。
6. 点击 Generate，下载 Word 报告。当前编辑项必须先 Save。

文字库包含 622 条 Observation 和 175 条 Recommendation，待确认的合并项保持独立。可在界面下载 Excel、修改后重新导入。Introduction、Recommended Remedial Works、Conclusion 和 Cost Estimate 保留空白供后续补充。Word 目录可能需要右键更新整个目录。

程序旁的 `WorkbenchData` 保存草稿、照片和导出报告。目录不可写时改存到 `%LOCALAPPDATA%/WMLInspectionWorkbench`；页面显示实际位置。可导出/导入草稿 ZIP 在不同电脑间迁移。每个人使用独立数据，不需要账号。

## 开发运行

使用 Windows x64、Python 3.12：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python workbench/app.py
```

自动打开浏览器，服务仅监听 `127.0.0.1`。可使用 `--no-browser`、`--port 8765`、`--data-dir .build/dev-data` 指定启动方式。页面右上角“退出程序”关闭服务。

## 构建 Windows 便携 ZIP

在干净 Windows 10/11 x64 环境安装 **64 位 Python 3.12**，在仓库根目录执行：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements.txt
.venv\Scripts\python.exe tools/package_workbench.py --build
```

一个命令完成 EXE 构建、ZIP 打包和解压后运行验证。输出：

- `outputs/workbench_v0.1.1/InspectionWorkbench.exe`
- `outputs/InspectionWorkbench_v0.1.1_Windows_x64.zip`
- `outputs/InspectionWorkbench_v0.1.1_Windows_x64.zip.sha256`

ZIP 包含程序、使用说明、许可证、应用源码及 HEIC 组件对应源码，不包含个人草稿和现场照片。程序内含界面、Word 模板、文字库和 HEIC 解码器。首次打包需要联网下载第三方源码，后续复用 `.build/source-cache`，每次校验 SHA-256。运行程序无需联网。

也可单独执行 `python tools/build_workbench.py` 构建 EXE，然后执行 `python tools/package_workbench.py` 打包，以及 `python tools/smoke_frozen_workbench.py` 验证当前版本 ZIP。以上命令需在已安装依赖的 Python 环境运行。

开发依赖只用于构建，最终用户不需要安装。请分发完整 ZIP，并保留其中的许可证和源码。打包脚本使用当前 Python 环境，不依赖原开发电脑的目录。HEIC wheel 与 `tools/heic_sources.json` 中的实际组件版本和源码校验值必须匹配；升级依赖时需同步核对该文件。

## GitHub 自动构建和发布

`.github/workflows/windows-portable.yml` 在 Windows runner 上安装固定依赖、执行应用测试、构建便携包，并从 ZIP 解压启动真正的 EXE，验证照片导入、草稿保存、Word 导出、备份恢复和退出。测试在含中文及空格的临时目录运行，并移除 Python 环境变量及 PATH 中的开发环境路径。

- 推送 `main`、`master` 或 `codex/**` 分支、提交 PR：构建并在 Actions 保存 `windows-portable-x64` 附件。
- 手动运行 Actions 工作流：只生成下载附件，不发布 Release。工作流需先进入仓库默认分支，才会在默认分支显示手动运行按钮。
- 推送 `v版本号` 标签：验证标签与 `workbench/version.py` 一致，通过全部检查后自动创建 GitHub Release，上传便携 ZIP 和 SHA-256。重跑时更新该版本的同名附件。

首次发布当前版本（先将本次修改提交并推送到远程分支）：

```powershell
git tag v0.1.1
git push origin v0.1.1
```

后续发布先修改 `workbench/version.py` 中的版本号，并更新 README 的版本及输出示例，再提交、推送对应标签，例如 `v0.1.2`。无需上传 `outputs/` 到 Git，也无需额外配置发布 Token；发布 job 使用 GitHub 提供的 `GITHUB_TOKEN`，仅该 job 请求 `contents: write`。仓库须允许 GitHub Actions 运行。


## 验证

```powershell
python workbench/test_workbench.py
```

覆盖 HEIC、EXIF 方向、原图保留、保存与备份、Excel 文字库、Word 模板和多照片导出。若本地存在历史原报告，测试会额外对比原模板；仅克隆此仓库时验证已保存模板和固定版式尺寸。

0.1.1 修复正文分节边距和检查表宽度：正文左右约 17.5 / 15 mm，主要检查表约 172.4 mm；照片保留比例并按照片列宽显示。纸张、封面、字体和页脚沿用模板。文字和照片会影响分页。

## 文件

- `workbench/app.py`：本地服务、照片和草稿管理。
- `workbench/report_engine.py`：保留模板 OOXML 格式的 Word 报告生成。
- `workbench/web/`：浏览器工作台界面。
- `workbench/resources/`：运行所需模板、Excel 文字库和下拉选项。
- `tools/`：历史报告提取、文字库分析、版式检查和构建辅助脚本。部分脚本需要本地历史报告、分析数据或 QA 输出。

Git 不包含历史报告全集、提取出的原报告全文、现场原图、个人草稿、构建缓存或生成报告。运行所需模板及文字库作为项目资源保留。

## 许可证

应用程序源码采用 GPL-2.0-or-later，见 `LICENSE`。模板、公司图案、文字库、照片和生成报告属于独立用户数据，不因此重新授权。第三方组件适用各自许可证，见 `LICENSES/`。HEIC wheel 含 GPL/LGPL 组件，对外分发时应一并提供许可证和对应源码；便携分发包的打包脚本处理这些文件。
