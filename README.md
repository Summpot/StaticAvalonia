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

## Build, package, and publish

Native compilation, NuGet assembly, and publication are separate workflows:

| Workflow | Input | Output |
| --- | --- | --- |
| **Build - SkiaSharp Static Libraries** (`build-skiasharp.yml`) | Upstream SkiaSharp ref | Six-runtime SkiaSharp/HarfBuzzSharp component bundle |
| **Build - ANGLE Static Libraries** (`build-angle.yml`) | Pinned ANGLE source | Windows x64/ARM64 ANGLE component bundle |
| **Package - StaticAvalonia** (`package-staticavalonia.yml`) | Two exact component tags and consumer versions | Tested NuGet package candidate |
| **Publish - StaticAvalonia** (`build-static-libs.yml`) | One exact package candidate tag | NuGet.org package and public GitHub Release |

Both native producers calculate independent identities from the upstream commit,
patches, GN arguments, build scripts, and workflow/toolchain configuration. An
existing matching component is reused. Changing package documentation or Avalonia
versions does not invalidate native components; changing a component's own build
recipe does.

Successful producer runs on `main` persist component ZIPs and SHA-256 manifests in
prereleases named `native-skiasharp-<digest>` and `native-angle-<digest>`. These are
durable build inputs, not Actions artifacts with a limited retention period. PR
builds upload Actions artifacts for validation without publishing component releases.
Component assets are never overwritten.

Packaging downloads two exact component releases, checks archive and file hashes,
and assembles `Summpot.StaticAvalonia`. It then publishes and runs a Windows x64
NativeAOT smoke application from an isolated directory containing only its EXE.
After this succeeds on `main`, the original `.nupkg` and its receipt are saved in a
`package-staticavalonia-<version>-<digest>` prerelease.

Publication downloads that tested candidate and verifies its hash. It does not
compile native code or repack the package. Retrying publication uses the same bytes.
If the NuGet version already exists, its contents must match the candidate; a different
payload requires a new revision. Public GitHub Releases are created only after the
matching package is available on NuGet.org.

Keep NuGet Trusted Publishing configured for `.github/workflows/build-static-libs.yml`.
That filename is retained for the publishing workflow, so its OIDC identity does not
change. The package ID remains **Summpot.StaticAvalonia**.

## Automatic releases

**Auto - Avalonia Release** checks Avalonia every six hours. It resolves the required
SkiaSharp commit, checks both independent component releases, builds only missing
components, packages and tests their combination, and calls the publishing workflow.
It does nothing when the same combination is already published.

The workflow can also be started manually for an exact `avalonia_version` and
`revision`. Scheduled runs use `STATICAVALONIA_REVISION`, a repository variable,
or `r1` when unset. Increment the revision when changing artifacts or package
contents for an already published version.

HarfBuzzSharp native sources come from the SkiaSharp commit, so those two libraries
share one native producer. The consumer HarfBuzzSharp version is recorded separately.
ANGLE remains pinned independently in `native/angle/source.json`.

See [the workflow guide](documentation/dev/avalonia-static-linking.md) for manual
build, packaging, and publication commands.

## Validation

```console
python -m unittest discover -s tests -v
```

Tests cover component invalidation, immutable releases, archive integrity, NuGet
version conflicts, version resolution, patches, package contents, and NativeAOT build items. ANGLE CI also links a native smoke executable for both
Windows architectures and runs the x64 executable.

## Licenses

Build scripts and packaging use the [MIT license](LICENSE.txt). ANGLE retains its
[BSD license](native/angle/LICENSE.txt); its dependency notices are collected from
the source checkout and included in the package. SkiaSharp, Skia, HarfBuzz, and their
dependencies retain their respective licenses.
