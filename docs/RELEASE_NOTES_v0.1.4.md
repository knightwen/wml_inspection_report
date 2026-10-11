提供两个 Windows 10/11 x64 便携包，下载发布附件，完整解压后运行 EXE：

- `InspectionWorkbench_v0.1.4_Windows_x64.zip`：保留中文，可在页头切换英文；运行 `InspectionWorkbench.exe`。
- `InspectionWorkbenchEnglish_v0.1.4_Windows_x64.zip`：独立纯英文版，界面、示例人员、Excel 措辞库说明与使用说明均为英文；运行 `InspectionWorkbenchEnglish.exe`。

精简并按等级排序：Likelihood 为 Unlikely / Possible / Likely，Severity 为 Negligible / Minor / Moderate / Severe，Priority 为 Low / Moderate / High / Urgent。支持手动填写；既有草稿的历史评级和文字保持不变。

英文版使用独立的 `WorkbenchDataEnglish`；中英文切换版沿用 `WorkbenchData`。升级前退出程序并保留数据目录，可通过草稿备份导入迁移报告和照片。人员库可另行复制 `personnel.json`。

编辑及生成 DOCX 无需安装 Python 或 Word。实际分页预览需要已安装并激活 Microsoft Word。请下载上述发布附件，GitHub 自动提供的 Source code ZIP 仅为源码。

---

Two portable Windows 10/11 x64 editions are available. Extract the complete ZIP and run its EXE:

- **InspectionWorkbench**: Chinese and English interfaces, with a language menu.
- **InspectionWorkbenchEnglish**: fixed English interface, English example personnel, Excel library instructions and usage guide.

Standard ratings have been simplified and ordered from low to high. Custom entries and historical draft values are preserved. Switching interface language saves the draft and preserves report text, names and photo captions as entered.

The English edition stores data in `WorkbenchDataEnglish`; the bilingual edition retains `WorkbenchData`. Exit the program and keep your data folder when upgrading. Export/import a draft backup to transfer reports and photographs between editions; copy `personnel.json` separately for the personnel library.

No Python or Word installation is required to generate DOCX reports. Actual paginated preview requires installed and activated Microsoft Word. Both packages include licenses, application sources and required third-party sources. SHA-256 files accompany both downloads.
