# Inspection Workbench v0.1.6

修复 Word 封面编号遗漏项目编号的问题。项目编号 `12477` 与报告编号 `SIR-004` 现在显示为 `12477-SIR-004`；报告编号已含该项目前缀时不会重复添加。保留原有封面样式、其他报告信息及子项布局，并兼容旧模板。

- `InspectionWorkbench_v0.1.6_Windows_x64.zip`：中文和英文切换版，运行 `InspectionWorkbench.exe`。
- `InspectionWorkbenchEnglish_v0.1.6_Windows_x64.zip`：纯英文版，运行 `InspectionWorkbenchEnglish.exe`。

解压完整 ZIP 后运行。升级前退出旧程序，备份草稿并保留原数据目录；已有 Word 文件需重新生成才能应用修复。

## English

Fixed the Word cover reference omitting the project number. Project `12477` and report `SIR-004` now display as `12477-SIR-004`. Report numbers already carrying the project prefix are kept without duplicating it. Cover formatting, other metadata and subitem layouts are preserved, including compatibility with older templates.

Both the bilingual and English-only Windows x64 portable editions include this fix. Extract the complete ZIP and run the corresponding EXE. Before upgrading, exit the previous program, back up drafts and retain the existing data folder. Regenerate existing Word reports to apply the corrected cover reference.

Validation includes application tests, English asset checks, browser regression checks, Open XML validation and report export from both packaged EXEs. The corrected nine-page report was also rendered and inspected using Microsoft Word locally.
