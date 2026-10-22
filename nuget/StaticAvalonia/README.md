# Summpot.StaticAvalonia

SkiaSharp and HarfBuzzSharp static libraries for Windows, Linux, and macOS NativeAOT
applications, plus Windows ANGLE static libraries for Avalonia's Direct3D backend.

## Usage

Add this package to your Avalonia application project:

```xml
<PackageReference Include="Summpot.StaticAvalonia" Version="3.119.4-avalonia.12.1.4-r1" />
```

Enable NativeAOT publishing:

```bash
# Windows x64
dotnet publish -r win-x64 -c Release /p:PublishAot=true

# Windows arm64
dotnet publish -r win-arm64 -c Release /p:PublishAot=true

# Linux x64
dotnet publish -r linux-x64 -c Release /p:PublishAot=true

# Linux arm64
dotnet publish -r linux-arm64 -c Release /p:PublishAot=true

# macOS
dotnet publish -r osx-arm64 -c Release /p:PublishAot=true
```

The package adds NativeAOT `DirectPInvoke` entries for `libSkiaSharp`,
`libHarfBuzzSharp`, and, on Windows, `av_libGLESv2.dll`. It also supplies the static
archives and required system linker arguments. ANGLE is included for `win-x64` and
`win-arm64`; SkiaSharp and HarfBuzzSharp are included for all six desktop runtimes.

Managed Avalonia, SkiaSharp, and HarfBuzzSharp packages are supplied by your
application. Match their versions to the native build and test drawing and text
shaping after publishing. Linux builds still require system fontconfig and FreeType;
macOS builds use system frameworks.

ANGLE is built from Chromium 7151. Its license and dependency notices are included
under `licenses/`, and its source pin is recorded in `build/ANGLE-source.json`.
