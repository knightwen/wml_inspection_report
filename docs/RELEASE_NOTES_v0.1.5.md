两个 Windows 10/11 x64 便携版同步支持检查子项。下载对应 ZIP，完整解压后运行 EXE：

- `InspectionWorkbench_v0.1.5_Windows_x64.zip`：保留中文和英文切换，运行 `InspectionWorkbench.exe`。
- `InspectionWorkbenchEnglish_v0.1.5_Windows_x64.zip`：独立纯英文版，运行 `InspectionWorkbenchEnglish.exe`。

每个检查项共用 Element、Condition Rating、Likelihood、Severity 和 Priority。通过“添加子项”分别录入照片、Observation 和可留空的 Recommendation；每个子项支持多张照片、照片命名和编辑、增删、拖动排序及前后移动。完成后保存整个检查项。

Word 每个检查项只输出一组评级，照片连续编号，例如 1.1、1.2、1.3。同一子项的多张照片纵向合并右侧描述单元格，不同子项的描述分开；表格跨页时重复评级表头。实际 Word 预览已验证多照片、独立描述和跨页合并。

旧草稿自动转换成一个子项，打开时不改写原文件，下次保存才更新。备份和恢复包含全部子项、照片及原图。升级前退出程序、备份草稿并保留数据目录。包含子项的新草稿需使用 0.1.5 或更高版本，不能回到 0.1.4 或更早版本编辑。

生成 DOCX 不需要安装 Python 或 Word；实际分页预览需要已安装并激活 Microsoft Word。两个 ZIP 均附 SHA-256 校验文件、许可和源码，不包含个人草稿或现场照片。

---

Both portable Windows 10/11 x64 editions now support inspection subitems. Extract the complete ZIP and run its EXE. InspectionWorkbench retains Chinese and English interfaces; InspectionWorkbenchEnglish always uses English.

Each inspection item shares Element, Condition Rating, Likelihood, Severity and Priority. Add independently described subitems, each with one or more photographs, an Observation and an optional Recommendation. Select, add, remove and reorder subitems with drag handles or earlier/later buttons. Captions and photo editing remain available within each subitem. Save the entire inspection item when complete.

Word numbers photographs continuously within each item. Multiple photographs in a subitem share a vertically merged description cell; the next subitem starts a separate description. Shared rating headers repeat across pages. Actual Microsoft Word preview was checked for grouped photographs, independent wording and pagination.

Older drafts migrate to one subitem per item without rewriting the file on open. Draft backups include all subitems, photographs and originals. Exit the program, back up drafts and retain the data folder before upgrading. Drafts containing subitems require version 0.1.5 or newer and cannot be edited with 0.1.4 or earlier.

Generating DOCX requires neither Python nor Word; actual paginated preview requires installed and activated Microsoft Word. Both packages include SHA-256 checksums, licenses and source code. Personal drafts and site photographs are excluded.
