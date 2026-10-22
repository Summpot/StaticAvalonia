# SkiaSharp.Static

为 Avalonia NativeAOT 应用构建和分发 SkiaSharp、HarfBuzzSharp 原生静态库。
本仓库维护构建配置、NuGet 打包工程和可选补丁；上游源码仅在构建时获取。

## 支持的平台

Windows、Linux 和 macOS，均包含 x64、ARM64。NuGet 包名为
`Summpot.SkiaSharp.Static`，使用方式见 [静态链接指南](documentation/dev/avalonia-static-linking.md)。

## 构建

在 GitHub Actions 中运行 **Build - SkiaSharp & HarfBuzzSharp Static Libraries**：

- `skiasharp_version`：与应用引用一致的 SkiaSharp 包版本。
- `skiasharp_ref`：`mono/SkiaSharp` 的提交、tag 或分支，默认 `release/3.119.4`。
- `harfbuzz_version`：应用引用的 HarfBuzzSharp 版本，用于发布说明；原生源码由 SkiaSharp 提交决定。
- `avalonia_version`：目标 Avalonia 版本。
- `revision`：包修订号，默认 `r1`。
- `publish_release`、`publish_nuget`：控制发布；仅验证构建时将两者关闭。

工作流在开始时将上游引用解析为一个提交，所有平台使用同一提交以及该提交固定的
`mono/skia` 子模块。源码、依赖和构建输出不提交到本仓库。上游源码需要修改时，
使用 [补丁目录](patches/README.md)。构建参数直接维护在 `native/static/`。

**Auto - Avalonia Update Watcher & Static Release** 每六小时检查 Avalonia 新版本，
读取其依赖版本并从上游解析对应 SkiaSharp 提交。无法确定版本时停止，避免用 `main`
或默认版本代替。无需镜像上游分支或标签，也无需每日合并上游源码。

NuGet 发布需要为此仓库配置 Trusted Publishing，并允许工作流获得 OIDC token。
继续使用现有仓库 URL 时可保留原有发布身份配置。

## 验证

```console
python -m unittest discover -s tests -v
```

此命令验证版本解析和补丁应用。完整原生编译在 GitHub Actions 的各平台执行；
新增补丁后还需验证 NativeAOT 应用的链接、绘图与文字整形。

## 许可证

构建脚本和打包配置使用 [MIT 许可证](LICENSE.txt)。
SkiaSharp、Skia、HarfBuzz 及其依赖遵循各自许可证；分发原生库时需保留相应许可声明。
