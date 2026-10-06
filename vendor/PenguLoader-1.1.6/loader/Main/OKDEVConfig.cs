using System;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

namespace PenguLoader.Main
{
    // OKDEV-only adapter: the loader remains official, but OKDEV needs the core
    // activation state mirrored into its existing config.ini.
    internal static class OKDEVConfig
    {
        // OKDEV passes its config.ini: the desktop user's, which core.dll reads in
        // the League client. This process runs elevated, and when OKDEV was
        // elevated with another account, LocalApplicationData is that account's.
        private static string ConfigPath
        {
            get
            {
                var fromOKDEV = Environment.GetEnvironmentVariable("OKDEV_CONFIG_PATH");
                if (!string.IsNullOrWhiteSpace(fromOKDEV))
                    return fromOKDEV;

                return Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "OKDEV",
                    "config.ini");
            }
        }

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool WritePrivateProfileString(
            string section,
            string key,
            string value,
            string filePath);

        public static void SetLoaderState(bool active)
        {
            var directory = Path.GetDirectoryName(ConfigPath);
            if (!Directory.Exists(directory))
                Directory.CreateDirectory(directory);

            // Without a BOM the INI API creates ANSI files and loses characters
            // outside the current system code page in Windows user names.
            if (!File.Exists(ConfigPath))
            {
                try
                {
                    using (var stream = new FileStream(ConfigPath, FileMode.CreateNew, FileAccess.Write))
                    {
                        var preamble = Encoding.Unicode.GetPreamble();
                        stream.Write(preamble, 0, preamble.Length);
                        stream.Flush(true);
                    }
                }
                catch (IOException)
                {
                    if (!File.Exists(ConfigPath)) throw;
                }
            }

            var loaderPath = active
                ? AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                : string.Empty;

            if (!WritePrivateProfileString("General", "disabled", active ? "0" : "1", ConfigPath) ||
                !WritePrivateProfileString("General", "loaderpath", loaderPath, ConfigPath))
            {
                throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not update OKDEV config.ini.");
            }
        }
    }
}
