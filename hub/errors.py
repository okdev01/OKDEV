"""Actionable public errors without raw paths, URLs, headers or credentials."""
import errno
import zipfile

import requests


def message(error, fallback='İşlem tamamlanamadı. Bağlantıyı ve dosyayı kontrol edip tekrar deneyin.'):
    if isinstance(error, requests.Timeout):
        return 'Sunucu zamanında yanıt vermedi. Bağlantını kontrol edip yeniden dene.'
    if isinstance(error, requests.ConnectionError):
        return 'Sunucuya bağlanılamadı. İnternet bağlantını kontrol edip yeniden dene.'
    if isinstance(error, requests.RequestException):
        return 'Kaynak sunucu isteği tamamlayamadı. Birazdan yeniden dene veya kaynak sayfasını kontrol et.'
    if isinstance(error, OSError) and (error.errno == errno.ENOSPC or getattr(error, 'winerror', None) == 112):
        return 'Diskte yeterli boş alan yok. Sistem durumu bölümünden alanı kontrol edip yeniden dene.'
    if isinstance(error, PermissionError):
        return 'Dosyaya erişilemiyor. Başka bir program dosyayı kullanıyor olabilir; klasör izinlerini de kontrol et.'
    if isinstance(error, FileNotFoundError):
        return 'İşlem için gerekli dosya bulunamadı. Dosyayı yeniden seç veya kütüphaneyi yenile.'
    if isinstance(error, zipfile.BadZipFile):
        return 'Mod paketi bozuk veya okunabilir bir ZIP değil. Dosyayı yeniden indirip dene.'
    if isinstance(error, ValueError):
        return str(error)[:500] or fallback
    return fallback
