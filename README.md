# StaticAvalonia

Static native libraries for Avalonia NativeAOT applications, distributed together as
**`Summpot.StaticAvalonia`**. This repository contains build configurations, packaging,
and source patches. Upstream source code is fetched only during builds.

## Libraries and platforms

| Runtime | SkiaSharp | HarfBuzzSharp | ANGLE |
| --- | --- | --- | --- |
| `win-x64`, `win-arm64` | Static | Static | Static, Direct3D |
| `linux-x64`, `linux-arm64` | Static | Static | Not included |
| `osx-x64`, `osx-arm64` | Static | Static | Not included |

ANGLE is built from the pinned Chromium 7151 source in
[`native/angle/source.json`](native/angle/source.json). Its complete static archives
and dependency patches follow [2ndlab/ANGLE.Static](https://github.com/2ndlab/ANGLE.Static).
Updating Avalonia does not automatically change this ANGLE source pin.

## Usage

```xml
<PropertyGroup>
  <PublishAot>true</PublishAot>
</PropertyGroup>
<ItemGroup>
  <PackageReference Include="Summpot.StaticAvalonia" Version="3.119.4-avalonia.12.1.4-r1" />
</ItemGroup>
```

Publish for one of the supported runtimes:

```console
dotnet publish -c Release -r win-x64
```

The package supplies the native archives, linker dependencies, and `DirectPInvoke`
entries for SkiaSharp and HarfBuzzSharp. On Windows it also supplies ANGLE's
`av_libGLESv2.dll` entry point used by Avalonia. Managed Avalonia, SkiaSharp, and
HarfBuzzSharp packages remain dependencies of your application.

Static linking these libraries does not make every system dependency static.
Linux still uses system fontconfig and FreeType; macOS uses system frameworks.
Use the managed dependency versions matching your native build and verify rendering
and text shaping in your published application.

## Automated builds

Run **Build - StaticAvalonia Native Libraries** in GitHub Actions. The workflow builds
all six runtimes, including Windows x64/ARM64 ANGLE, packages one NuGet package, and
optionally publishes its archives and package.

| Input | Purpose |
| --- | --- |
| `avalonia_version` | Target Avalonia version |
| `skiasharp_version` | SkiaSharp package version used in the package identity |
| `skiasharp_ref` | Upstream SkiaSharp commit, tag, or branch |
| `harfbuzz_version` | Consumer HarfBuzzSharp version recorded in release notes; native source comes from the SkiaSharp commit |
| `revision` | Package revision, such as `r1` |
| `publish_release`, `publish_nuget` | Disable both for a build without publication |
| `skip_native_builds` | Repack complete archives from an existing StaticAvalonia release |

All SkiaSharp platforms use the same resolved commit and its pinned `mono/skia`
submodule. ANGLE uses its own pinned commit. Its workflow can also be run separately
as **Build - ANGLE Static Libraries** for native build and link validation.

**Auto - Avalonia Update Watcher & Static Release** checks Avalonia releases every
six hours, resolves the managed dependency versions, and triggers the combined build.
Unknown versions fail instead of falling back to an unrelated branch.

Release tags use `staticavalonia-<AvaloniaVersion>-skia-<SkiaSharpVersion>-<revision>`.
Configure NuGet Trusted Publishing for **Summpot.StaticAvalonia**, this repository,
and `.github/workflows/build-static-libs.yml` before enabling NuGet publication.

## Validation

```console
python -m unittest discover -s tests -v
```

Tests cover version resolution, patches, archive architecture checks, package contents,
and NativeAOT build items. ANGLE CI also links a native smoke executable for both
Windows architectures and runs the x64 executable.

## Licenses

Build scripts and packaging use the [MIT license](LICENSE.txt). ANGLE retains its
[BSD license](native/angle/LICENSE.txt); its dependency notices are collected from
the source checkout and included in the package. SkiaSharp, Skia, HarfBuzz, and their
dependencies retain their respective licenses.
