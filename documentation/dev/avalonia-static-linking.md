# StaticAvalonia workflow guide

The package `Summpot.StaticAvalonia` contains SkiaSharp and HarfBuzzSharp for six
desktop runtimes and ANGLE for Windows x64/ARM64. Consumers enable NativeAOT and
reference the package alongside their managed Avalonia dependencies.

```xml
<PropertyGroup>
  <PublishAot>true</PublishAot>
</PropertyGroup>
<ItemGroup>
  <PackageReference Include="Summpot.StaticAvalonia" Version="3.119.4-avalonia.12.1.4-r1" />
</ItemGroup>
```

## Native component builds

SkiaSharp and HarfBuzzSharp share one producer because their native source versions
are selected together by the upstream SkiaSharp checkout. ANGLE has a separate
producer and source pin.

```console
gh workflow run build-skiasharp.yml -f skiasharp_ref=release/3.119.4
gh workflow run build-angle.yml
```

Use `gh run list --workflow <workflow-file>` to find the run, then
`gh run watch <run-id> --exit-status` to wait for validation.

Each producer checks its component identity before compiling. The identity includes
the exact source commit and component-specific patches, GN parameters, scripts, and
workflow/toolchain configuration. Existing matching releases are reused. New builds
on `main` persist `component.json` and a native ZIP under a `native-<component>-<digest>`
prerelease, without marking it as the latest public release. PRs upload validation
artifacts without writing releases.

Manifests bind every file and the complete ZIP to SHA-256 hashes and record the
producer repository, workflow, commit, and run. A conflicting release asset is an
error; workflows never overwrite existing component releases. Keep the native
component releases referenced by package receipts.

## Package an exact combination

Choose the exact native component tags from their producer outputs or GitHub Releases.

```console
gh workflow run package-staticavalonia.yml \
  -f skiasharp_tag=native-skiasharp-<digest> \
  -f angle_tag=native-angle-<digest> \
  -f avalonia_version=12.1.4 \
  -f harfbuzz_version=8.3.1.3 \
  -f revision=r1
```

Packaging verifies both component inventories and hashes before assembly. It does
not call either native compiler. Missing libraries and conflicting files stop the
operation. The package includes both component manifests under `build/components/`.

A Windows x64 NativeAOT consumer checks SkiaSharp pixel rendering, HarfBuzzSharp
buffer operations, and ANGLE entry-point lookup. Only its EXE is copied into the
execution directory. After successful validation on `main`, the exact package and
`package.json` are saved under `package-staticavalonia-<version>-<digest>`.
Repeating the same packaging request reuses that candidate instead of repacking.

The package identity is `<SkiaSharpVersion>-avalonia.<AvaloniaVersion>-<revision>`.
For an already published version, changes to native components or package contents
require a new revision.

## Publish the tested candidate

```console
gh workflow run build-static-libs.yml \
  -f package_tag=package-staticavalonia-<version>-<digest>
```

The publishing workflow keeps this filename to preserve the configured NuGet
Trusted Publishing identity. It accepts one exact tested candidate tag, downloads
and verifies the original package, and pushes those bytes to NuGet.org. It neither
builds components nor runs `dotnet pack`.

An existing NuGet version is accepted only if its package contents match the
candidate, allowing NuGet's repository signature. After the matching public package
is confirmed, the workflow creates the final `staticavalonia-*` GitHub Release.
If NuGet or GitHub publication fails, rerun publication with the same candidate tag.

## Automatic coordination

`auto-avalonia-sync.yml` checks the latest Avalonia release every six hours or accepts
an explicit Avalonia tag when run manually. It resolves component identities, skips
existing native builds, packages and tests the exact pair, and publishes the candidate.
An already published identical combination is skipped. No workflow uses a floating
`latest` native artifact or substitutes an unrelated upstream branch.

Scheduled runs use repository variable `STATICAVALONIA_REVISION`, defaulting to `r1`.
Manual runs accept a `revision` input. Update it when replacing published contents.

## Runtime dependencies

Static SkiaSharp, HarfBuzzSharp, and ANGLE archives do not make all system libraries
static. Linux still links fontconfig and FreeType; macOS uses system frameworks.
Avalonia's normal Linux/macOS desktop renderers do not need the Windows ANGLE build.
Validate drawing and text shaping with the managed dependency versions used by the
application.
