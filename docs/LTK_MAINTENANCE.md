# OKDEV / LTK bakım rehberi

Bu sürüm resmî LTK çalışma bileşenini kullanır. LTK'dan bağımsız değildir.
Gelecekteki League veya LTK değişikliklerine karşı bozulmama garantisi yoktur;
ama uyumluluk bilgileri, teşhis ve onarım ayrı tutulur.

## Kullanım

- `Kontrol.cmd`: çevrimdışı kontrol; oyun başlatmaz. Sonuç `%LOCALAPPDATA%/OKDEV/logs/maintenance.json` dosyasına yazılır.
- `Onar.cmd`: resmî teslimat önbelleğini doğrular; gerektiğinde resmî LTK eşitlemesini dener. Oyun ve OKDEV kapalıyken kullanın.
- EXE ile aynı klasördeki `_internal` klasörünü koruyun.
- `ready: true`, çalışma dosyalarının doğrulandığını belirtir. Oyun içi kostüm görüntüsünün çalıştığı anlamına gelmez; bunun için ayrıca antrenman testi gerekir.
- Uyumlu yeni DLL aynı desteklenen protokolü kullanıyorsa tekrar OKDEV derlemesi gerekmez. Host veya protokol değişirse aşağıdaki kod incelemesi gerekir.

## Güncelleme yaparken

1. `https://github.com/LeagueToolkit/ltk-manager` sürümünü, host protokolünü ve teslimat değişikliklerini inceleyin. İncelenen commit ve sürümü kaydedin.
2. Resmî kurulum dosyasını GitHub sürümünden alın, yayımlanan SHA256 ile doğrulayın. İçindeki host dosyasının SHA256 değerini hesaplayın.
3. `okdev_ltk_policy.py` içindeki sürüm, kurulum URL/digest, host digest ve protokol sabitlerini birlikte güncelleyin. Protokol değiştiyse önce `okdev_ltk_delivery.py` ve çalışma entegrasyonunu uyarlayın; yalnızca sürüm sayısını artırmayın.
4. İmzalı manifest, dosya boyutu ve SHA256, iptal listesi, desteklenen manager aralığı ve oyun derleme/EOL kontrollerini koruyun. İmzalı EOL için DLL makine kodunda sabit desen aramayın. Geçersiz imzalı teslimatı eski doğrulama yöntemine düşürmeyin.
5. `powershell -ExecutionPolicy Bypass -File scripts/build_maintenance.ps1` testleri çalıştırır ve bakım paketini üretir. Ardından `.venv/Scripts/python.exe -m PyInstaller --noconfirm --distpath output/maintained-client --workpath build/maintained-client OKDEV.spec` ile uygulamayı derleyin.
6. Paketlenmiş bakım EXE'sini `diagnose` ile çalıştırın; raporu inceleyin. Oyun kapalıyken onarımı, ardından ayrı antrenman oturumunda görüntüyü test edin. Oyun testini yapmadan çalıştığını ilan etmeyin.
7. Kurulu sürüme geçişte mevcut işlemsel güncelleyiciyi ve yedeğini kullanın; açık oyun/istemci dosyalarının üstüne kopyalamayın. Kullanıcı ayarlarını koruyun. Yerel derleme internette yayımlanmış sürüm değildir.

Teslimat tokenlarını veya kullanıcı önbelleğini paketlemeyin. Teşhis raporu yalnızca genel sürüm ve doğrulama bilgilerini içerir. Ağ/teslimat hatalarında mevcut dosyalar korunur; aynı başarısız teslimat 15 dakika boyunca yeniden indirilmez. Açık `repair` komutu geçici bekleme süresini aşabilir, uyumsuzluk ve güven kontrollerini aşamaz.

## 2026-11-04 yerel bakım düzeltmesi

İncelenen LTK manager commit: `efb8c177039d4ea22ef99da16a8867bfa7a5f53b`.
Desteklenen host: manager 1.33.0 / protokol 3.
Güncel resmî DLL'nin EOL değeri eski makine kodu deseniyle okunamıyordu.
EOL artık doğrulanmış imzalı manifestten alınır; DLL'nin boyutu ve SHA256 değeri ayrıca doğrulanır.
İlgili 37 test geçti. Paketlenmiş bakım aracında resmî `ltk_patcher-30` doğrulandı.
Bu kayıt oyun içi görüntü testi değildir.
