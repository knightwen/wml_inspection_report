# WML Inspection Report Workbench

本地检查报告工作台，当前版本 **0.1.1**。支持拖入多张现场照片、选择并编辑 Observation / Recommendation、保存检查项，并按 Word 模板生成 DOCX 报告。

## 使用

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

## 构建便携 EXE

```powershell
python tools/build_workbench.py
```

输出：`outputs/workbench_v0.1.1/InspectionWorkbench.exe`。构建会包含界面、Word 模板、文字库和 HEIC 解码器。

开发依赖只用于构建，最终用户不需要安装。分发完整便携包时保留第三方许可证及 HEIC 组件对应源码；`tools/package_workbench.py` 是当前本地工作环境使用的打包辅助脚本。

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
