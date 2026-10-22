# Source patches

Patches are applied in filename order, with `git apply --check` before each change.
A failed patch stops the build. Use numbered filenames to keep the order explicit.

| Directory | Target | Timing |
| --- | --- | --- |
| `skiasharp/*.patch` | SkiaSharp root | After dependency synchronization |
| `skia/*.patch` | SkiaSharp's `externals/skia` | After dependency synchronization |
| `angle/deps/*.patch` | ANGLE root | Before `gclient sync` |
| `angle/build/*.patch` | ANGLE root | After `gclient sync`, before compilation |

The ANGLE patches target commit `df9c59dcacff7d186d00e3263a1aa68f8059137c`
on `chromium/7151`. They are adapted from
[2ndlab/ANGLE.Static at 79e529b](https://github.com/2ndlab/ANGLE.Static/tree/79e529b56b7c6b3a3762ab0cfabc8ff99b2b6687):

- The dependency patch omits unused test, SwiftShader, Dawn, and LLVM source trees
  for the MSVC build with Vulkan and WebGPU disabled.
- The build patch creates a complete `libANGLE_static` archive and includes
  transitive dependencies in `libGLESv2_static`.

There are currently no SkiaSharp or Skia patches. GN arguments, NuGet targets, and
workflows are maintained as ordinary files. Changes to native artifacts require a
new package revision.
