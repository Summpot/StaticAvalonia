# 可选源码补丁

当前不包含源码补丁。GN 参数、NuGet targets 和工作流作为普通文件维护。

需要修改源码时，将补丁放在以下目录，按文件名排序应用：

- `patches/skiasharp/*.patch`：相对 `mono/SkiaSharp` 仓库根目录。
- `patches/skia/*.patch`：相对其 `externals/skia` 子模块根目录。

使用 `0001-description.patch` 等编号明确顺序。每个补丁应说明适用的上游版本及用途，
保持修改范围最小。工作流在同步 Skia 依赖后、编译前检查并应用补丁，失败时停止构建。
补丁导致的产物变化应使用新的包修订号发布。
