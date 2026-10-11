# WML Inspection Report Workbench

本地检查报告工作台，当前版本 **0.1.3**。支持拖入多张现场照片、选择并编辑 Observation / Recommendation、保存检查项，并按 Word 模板生成 DOCX 报告。

当前工作区已完成第一阶段稳定性改进，并更新本地预览；版本号暂不变，尚未创建新标签或发布新版本。本地构建包仅用于验证。

后续工作与验收要求见 [改进计划](docs/IMPROVEMENT_PLAN.md)。开发分支更新与版本发布分开，发布新版本需另行确认。

## 使用

从 [GitHub Releases](https://github.com/knightwen/wml_inspection_report/releases/latest) 下载 `InspectionWorkbench_v版本号_Windows_x64.zip`。请下载发布附件中的便携 ZIP；GitHub 自动生成的 `Source code (zip)` 只有源码。首次发布完成后此入口才会有下载包。

Windows 10/11 64 位便携程序：解压完整分发包，双击 `InspectionWorkbench.exe`，在自动打开的本地浏览器中操作。编辑草稿和生成 DOCX 无需安装 Python、Word 或照片编解码器。逐页预览需要本机安装并激活 Microsoft Word；未检测到或转换失败时会说明原因，仍可生成 DOCX。

1. 填写报告信息和封面信息，从人员库选择作者和审阅者，自动填写资质与职位。
2. 拖入 JPG、PNG、WEBP、HEIC 或 HEIF；一个检查项可包含多张照片，可旋转和调整顺序。点击照片下方“编辑”，支持框选裁剪、画红圈、撤销及重置本次编辑。先“保存照片”，再点击 Save 保存检查项；Word 使用编辑后的照片，原始文件仍保留。照片名称可留空，填写后显示在 Word 照片下方。
3. 填写 Element、Condition Rating、Likelihood、Severity 和 Priority。下拉菜单始终显示全部标准选项；选择“手动填写 / 补充描述”可输入自定义内容。Severity 和 Priority 仅提供基本等级。
4. 搜索并选择 Observation / Recommendation，再按现场情况编辑。
5. 点击 Save，将检查项保存到列表；支持重新编辑、删除，拖动序号旁的手柄调整顺序并自动保存，也可使用 ↑ / ↓。
6. 在“报告章节”填写 Introduction、Recommended Remedial Works、Conclusion 和 Cost Estimate 说明，支持多段落、自动保存及手动保存。四个模块每行一个。费用说明填入原模板费用表上方；费用表支持增删行、Priority 下拉、Quantity × Rate 自动计算及总计，并写入 Word 原模板表格。数量或单价留空时仅显示已填写项小计。
7. 点击 Generate，下载 Word 报告。当前编辑项必须先 Save；已填写的章节同时导出，空白章节保留模板。

顶部保存状态区分未保存、等待保存、正在保存、保存失败及保存冲突。连续编辑时，全部修改提交成功后才显示“已保存到本地”；存在待提交或失败内容时，关闭或刷新页面会提示。保存失败可点击“重试保存”。两个页面修改同一草稿发生冲突时，可另存副本继续，或保留副本后加载最新版本，也可下载包含当前修改和照片的 ZIP。

预览在后台处理提交时的固定草稿快照，显示生成、Word 转换和逐页渲染进度。可以关闭预览窗口继续编辑及保存，再通过“查看预览进度 / 结果”重新打开。后续编辑不会改变已提交的预览；下载的 Word 与这份预览一致。失败时可以重试。转换超时会结束本次转换，并按进程身份和创建时间核对、清理本次创建的 Word 实例。

内置常用措辞库仅保留历史报告出现至少 **2 次**的描述：**90 条 Observation、44 条 Recommendation**，按历史频次排列，保留原编号与文字。一次性描述已从内置 JSON 和 Excel 删除，Excel 只包含两个常用措辞工作表。低频或专项情况可手动输入；选用现有措辞时按当前现场修改位置、编号和章节引用。可在界面下载 Excel、修改后重新导入。Introduction、Recommended Remedial Works、Conclusion 和 Cost Estimate 保留空白供后续补充。Word 目录可能需要右键更新整个目录。

从 0.1.1 升级：未修改过的旧默认库会在启动时自动替换为常用库，已有草稿和检查项保留完整文字。用户自行编辑或导入的自定义库继续使用原内容；如需改用内置常用库，可从本仓库 `workbench/resources/word_library.xlsx` 下载并在工作台导入。

程序旁的 `WorkbenchData` 保存草稿、照片和导出报告。目录不可写时改存到 `%LOCALAPPDATA%/WMLInspectionWorkbench`；页面显示实际位置。可导出/导入草稿 ZIP 在不同电脑间迁移。每个人使用独立数据，不需要账号。

在顶部 **人员库** 中新增、编辑或删除人员，填写姓名、Qualifications（资质）和 Title（职位），并选择作者、审阅者或两个角色。初始库提供“示例作者（请编辑）”和“示例审阅者（请编辑）”，资质与职位留空，使用前请换成实际人员。人员库保存在数据目录的 `personnel.json`，重启和升级时继续保留。

选择姓名后，资质与职位自动显示在姓名下方并用于报告，无需在报告信息中重复填写；资料在人员库统一维护，也可手动填写姓名。报告保存当时的人员信息；以后编辑或删除人员库中的条目不会改写既有报告。需要更新当前报告时重新选择人员。草稿 ZIP 包含报告中的人员资料；迁移整个可选人员库请同时复制数据目录中的 `personnel.json`。

切换为手动姓名时清除之前选择的人员引用、资质和职位，避免新姓名沿用上一人的资料。

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

- `outputs/workbench_v0.1.3/InspectionWorkbench.exe`
- `outputs/InspectionWorkbench_v0.1.3_Windows_x64.zip`
- `outputs/InspectionWorkbench_v0.1.3_Windows_x64.zip.sha256`

ZIP 包含程序、使用说明、许可证、应用源码及 HEIC 组件对应源码，不包含个人草稿和现场照片。程序内含界面、Word 模板、文字库和 HEIC 解码器。首次打包需要联网下载第三方源码，后续复用 `.build/source-cache`，每次校验 SHA-256。运行程序无需联网。

也可单独执行 `python tools/build_workbench.py` 构建 EXE，然后执行 `python tools/package_workbench.py` 打包，以及 `python tools/smoke_frozen_workbench.py` 验证当前版本 ZIP。以上命令需在已安装依赖的 Python 环境运行。

开发依赖只用于构建，最终用户不需要安装。请分发完整 ZIP，并保留其中的许可证和源码。打包脚本使用当前 Python 环境，不依赖原开发电脑的目录。HEIC wheel 与 `tools/heic_sources.json` 中的实际组件版本和源码校验值必须匹配；升级依赖时需同步核对该文件。

## GitHub 自动构建和发布

`.github/workflows/windows-portable.yml` 在 Windows runner 上安装固定依赖，执行应用测试、保存队列测试和浏览器回归，再构建便携包。测试从 ZIP 解压启动真正的 EXE，验证 HEIC 和照片编辑、保存冲突恢复、无 Word 场景下生成 DOCX、备份恢复、重复启动及只读程序目录的数据回退。测试在含中文及空格的临时目录运行，并移除 Python 环境变量及 PATH 中的开发环境路径。浏览器回归使用可控 Word 转换测试替身及真实 PDFium，真实 Microsoft Word 集成另在装有 Word 的本机验证。

- 推送 `main`、`master` 或 `codex/**` 分支、提交 PR：构建并在 Actions 保存 `windows-portable-x64` 附件。
- 手动运行 Actions 工作流：只生成下载附件，不发布 Release。工作流需先进入仓库默认分支，才会在默认分支显示手动运行按钮。
- 推送 `v版本号` 标签：验证标签与 `workbench/version.py` 一致，通过全部检查后自动创建 GitHub Release，上传便携 ZIP 和 SHA-256。重跑时更新该版本的同名附件。

首次发布当前版本（先将本次修改提交并推送到远程分支）：

```powershell
git tag v0.1.3
git push origin v0.1.3
```

后续发布先修改 `workbench/version.py` 中的版本号，并更新 README 的版本及输出示例，再提交、推送对应标签，例如 `v0.1.4`。无需上传 `outputs/` 到 Git，也无需额外配置发布 Token；发布 job 使用 GitHub 提供的 `GITHUB_TOKEN`，仅该 job 请求 `contents: write`。仓库须允许 GitHub Actions 运行。


## 验证

```powershell
python workbench/test_workbench.py
node tools/test_draft_state.cjs
powershell -File tools/validate_reports.ps1
```

20 项应用测试覆盖人员库快照与手动姓名清理、草稿冲突副本及未保存 ZIP、后台预览快照与并行保存、无 Word 和转换失败、超时清理与进程身份检查，以及常用库、HEIC、原图、照片编辑、备份和多照片 Word 模板。若本地存在历史原报告，测试会额外对比原模板；仅克隆此仓库时验证已保存模板和固定版式尺寸。

自动化浏览器回归需要开发用 Node.js 和 Playwright；最终用户不需要这些依赖。本机有 Edge 时执行：

```powershell
npm install --prefix .build/browser-deps --no-save --package-lock=false playwright@1.62.1
node tools/test_browser_workbench.cjs
```

先运行应用测试生成照片样本。浏览器回归使用独立测试数据，覆盖连续文字库选择、人员选择、照片标注、拖动排序、连续保存、关闭提示、保存失败重试、多页面冲突恢复、预览期间保存及预览失败重试。CI 使用 Playwright Chromium，可通过 `WML_TEST_BROWSER_CHANNEL=chromium` 指定。

安装并激活 Word 的正常 Windows 用户会话中，可运行 `python tools/test_native_preview.py` 验证真实转换。也可启动使用 `.build/qa/` 下独立数据目录的便携 EXE，再执行 `python tools/test_native_preview.py --server-data 数据目录 --shutdown`。此项检查实际 PDF 和逐页图、预览快照、保存不阻塞、已有 Word 进程保留及本次 Word 进程退出。无 Word 测试在当前本机通过禁用转换能力模拟；独立未安装 Word 的电脑复核保留为发布前验证。

Word 格式校验使用固定版本的微软 Open XML SDK，首次运行下载到 `.build/openxml-validator` 并校验 SHA-256。检查内置模板、多照片报告及旧模板修复回归报告，发现格式错误时失败；GitHub Actions 同时检查便携 EXE 导出的报告。该 SDK 仅用于开发验证，最终用户无需安装。

0.1.1 修复正文分节边距和检查表宽度：正文左右约 17.5 / 15 mm，主要检查表约 172.4 mm；照片保留比例并按照片列宽显示。纸张、封面、字体和页脚沿用模板。文字和照片会影响分页。

## 文件

- `workbench/app.py`：本地服务、照片和草稿管理。
- `workbench/preview.py`：后台预览任务、Word 能力检测与所创建进程的清理。
- `workbench/report_engine.py`：保留模板 OOXML 格式的 Word 报告生成。
- `workbench/web/`：浏览器工作台界面。
- `workbench/resources/`：运行所需模板、常用措辞 JSON / Excel、词库升级策略和下拉选项。
- `tools/build_common_word_library.mjs`：从内置 JSON 重建两页常用措辞 Excel（开发工具，使用 `@oai/artifact-tool`）。
- `tools/`：历史报告提取、文字库分析、版式检查和构建辅助脚本。部分脚本需要本地历史报告、分析数据或 QA 输出。

Git 不包含历史报告全集、提取出的原报告全文、现场原图、个人草稿、构建缓存或生成报告。运行所需模板及文字库作为项目资源保留。

## 许可证

应用程序源码采用 GPL-2.0-or-later，见 `LICENSE`。模板、公司图案、文字库、照片和生成报告属于独立用户数据，不因此重新授权。第三方组件适用各自许可证，见 `LICENSES/`。HEIC wheel 含 GPL/LGPL 组件，对外分发时应一并提供许可证和对应源码；便携分发包的打包脚本处理这些文件。

报告预览：点击“预览报告”查看已保存检查项的实际分页、文字和照片，并可下载此次预览对应的 Word。此功能使用本机已安装并激活的 Microsoft Word 转换 PDF，再逐页显示；生成 DOCX 本身不需要安装 Word。

照片编辑：支持拖动裁剪框与四角、自由或固定比例裁剪、左右旋转、圆圈／矩形／箭头／画笔标注、颜色与线宽、缩放和移动视图、撤销与重做（Ctrl+Z / Ctrl+Shift+Z）。点击“保存照片”后，再保存检查项即可加入报告；原始照片另存保留。
