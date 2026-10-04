# OKDEV

**Rose tabanlı, bağımsız sürümlenen Windows istemcisi.**

[Kurulumu indir](https://github.com/okdev01/OKDEV/releases/latest) · [MIT lisansı](LICENSE)

## Kurulum

1. Releases bölümünden `OKDEV_Setup_1.0.0.exe` dosyasını indirin ve açın.
2. LTK Manager veya Rose kurulum klasörünü seçin. İki patcher dosyası otomatik bulunur.
3. League of Legends klasörünü ve yeni bir OKDEV kurulum klasörünü seçin.
4. **Kontrol et ve kur** düğmesine basın. Kurulum dosyaları kopyalar ve isteğe bağlı masaüstü kısayolu oluşturur.
5. OKDEV'i açın; Windows yönetici izni isteyebilir. Önce antrenman modunda deneyin.

Python kurmanız gerekmez. Windows 10/11 x64, kurulu League of Legends ve kendi LTK patcher dosyalarınız gerekir. LTK dosyaları bu depoda veya kurulum paketinde dağıtılmaz.

## 1.0.0 değişiklikleri

- OKDEV uygulama adı, pencere başlıkları, EXE bilgileri ve masaüstü kısayolu.
- Türkçe klasör seçimli kurulum sihirbazı; yanlış ve uyumsuz dosyaları engeller.
- Patcher uyumluluğu bugünün tarihi yerine oyunun PE derleme tarihine göre kontrol edilir.
- Rose'un otomatik uygulama güncellemesi ve upstream telemetrisi kapalıdır.
- Sürüm ve yama dağıtımı bu deponun Releases bölümünden yönetilir.

## Sınırlar ve bağımlılıklar

Bu bir Rose fork'udur; özgün geliştirici atıfları ve MIT lisansı korunur. Pengu Loader, LTK ve mevcut oyun verisi kaynakları dış bağımlılıklardır. İç protokol ve eklenti adları ile `%LOCALAPPDATA%\Rose` veri klasörü uyumluluk için korunur; mevcut Rose ile aynı anda çalıştırmayın.

OKDEV'e ait bir relay yapılandırılana kadar Party Mode kullanılamaz. Solo kullanım bundan etkilenmez. Bu ilk sürüm otomatik OKDEV güncelleyicisi içermez; yeni kurulum dosyaları Releases üzerinden alınır. Kurulum mevcut dolu klasörün üzerine yazmaz; yeni sürümü yeni bir klasöre kurun.

15 otomatik test ve paketlenmiş kurulum arayüzü/içerik kontrolü geçti. Gerçek maç ve farklı bilgisayarda uçtan uca doğrulama henüz yapılmadı.

## Kaynaktan derleme

Python 3.12, Visual Studio C++ ve .NET masaüstü derleme araçları, .NET Framework 4.7.2 hedefleme paketi gerekir.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/build_pyinstaller.py
python scripts/build_okdev_setup.py
```

Uygulama `dist/OKDEV/`, kurulum EXE'si `release/` altında oluşur. Inno Setup gerekmez. Party relay için `party/network/relay_config.py` içinde `RELAY_URL` ayarlanabilir; varsayılan boş bırakılır.

GitHub Actions'ta **Build OKDEV** iş akışı elle çalıştırılabilir. Üretilen dosyalar önce test edilir, ardından Releases üzerinden yayımlanır. GitHub üzerindeki Windows derlemesi ve testler başarıyla tamamlanmıştır.

## Lisans ve atıf

Özgün proje: [Alban1911/Rose](https://github.com/Alban1911/Rose), Copyright (c) 2026 Alban and Florent, MIT. [Pengu Loader](https://github.com/PenguLoader/PenguLoader) lisansı `vendor/PenguLoader-1.1.6/LICENSE` içindedir. OKDEV, Riot Games tarafından onaylanmış bir proje değildir.
