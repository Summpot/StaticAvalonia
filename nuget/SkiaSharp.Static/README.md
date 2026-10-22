# SkiaSharp.Static

Statically linked native libraries of SkiaSharp and HarfBuzzSharp for Avalonia UI NativeAOT applications.

## Usage

Add this package to your Avalonia application project:

```xml
<PackageReference Include="Summpot.SkiaSharp.Static" Version="3.119.4-avalonia.12.1.2" />
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
