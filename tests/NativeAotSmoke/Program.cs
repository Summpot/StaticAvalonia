using System;
using System.Runtime.InteropServices;
using SkiaSharp;

using (var bitmap = new SKBitmap(2, 2))
{
    using var canvas = new SKCanvas(bitmap);
    canvas.Clear(SKColors.Red);
    if (bitmap.GetPixel(0, 0) != SKColors.Red)
        throw new Exception("SkiaSharp rendering failed.");
}

using (var buffer = new HarfBuzzSharp.Buffer())
{
    buffer.AddUtf8("hello");
    buffer.GuessSegmentProperties();
    if (buffer.Length != 5)
        throw new Exception("HarfBuzzSharp buffer failed.");
}

if (NativeMethods.GetProcAddress("eglGetDisplay") == IntPtr.Zero)
    throw new Exception("ANGLE entry point failed.");

Console.WriteLine("StaticAvalonia NativeAOT smoke passed.");

internal static class NativeMethods
{
    [DllImport("av_libGLESv2.dll", EntryPoint = "EGL_GetProcAddress", CharSet = CharSet.Ansi)]
    internal static extern IntPtr GetProcAddress(string name);
}
