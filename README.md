# OKDEV

Windows için bağımsız sürümlenen OKDEV istemcisi.

## 1.5.0: Arka plan indirmeleri ve kurtarılabilir kütüphane

İndirmeler ayrı kuyrukta ilerler; bu sırada arayüz kullanılabilir. **İndirmeler** bölümünde ilerleme, hız ve kalan süre görünür. Bekleyen veya indirilen paket iptal edilebilir, başarısız işler yeniden denenebilir. Uygulama kapanırken başlamış dosya yüklemesi tamamlanır. Bekleyen işler sonraki açılışta kendiliğinden ağ bağlantısı başlatmaz; yeniden başlatmak kullanıcıya bırakılır.

**Modlarım** kartlarındaki seçim kutuları birden fazla modu birlikte açıp kapatır. Uygulamadan önce hangi modların açılacağı ve kapanacağı gösterilir; aynı şampiyon/kategori için çakışan seçimler açıklanır. **Son seçimi geri al** önceki kombinasyona döner. Profiller dosya olarak dışa aktarılıp başka bir kurulumda içe aktarılabilir; eksik modlar önceden gösterilir. Profil dosyaları mod paketlerini içermez.

Mod ekleme, güncelleme, kaldırma ve geri yükleme işlemleri ani kapanmadan sonra kurtarılır. Eski dosyalar ve yarım kalan yeni paketler mümkün olduğunda geri yüklenebilir yedek olarak saklanır. Çakışmalı kayıtların üzerine yazılmaz. **Sistem durumu → Gelişmiş araçlar → Yarım işlemleri kurtar** yeniden kontrol eder. **Modlarım → Kaldırılan modlar ve sürüm yedekleri → Yedeği incele** dosya sayısını/boyutunu gösterir ve yedeği yeniden içe aktarılabilir `.fantome` paketi olarak kaydeder.

Son 200 işlem yalnızca yerel geçmişte tutulur. Büyük kütüphanelerde kartlar sayfalar halinde, görseller görünür oldukça yüklenir. Ayarlar ekranında uygulama sürümü, sürüm notları, destek ve kaynak kod bağlantıları bulunur.

Modlarım kategoriye ve eksik dosya durumuna göre filtrelenebilir. Görünüm dışında kalan toplu seçimlerin sayısı belirtilir; arka plan yenilemelerinde klavye odağı korunur. Profil ve destek raporu dışa aktarımları canlı kullanıcı verisinin üzerine yazamaz.

Yerel paket mevcut mod kimliğini kullanıyorsa eski ve yeni sürüm onaydan önce gösterilir. Güncelleme eski dosyaları yedekler; önizleme sırasında mod değişmişse güncel onay istenir. Bozuk veya aşırı büyümüş yerel kayıtlar özgün dosya korunarak bildirilir. Bildirimler klavyeyle veya kapatma düğmesiyle kapatılabilir.

Kurulum güncellemesi klasör değişimi sırasında kesilirse, **Setup veya güncellemeyi aynı hedef klasöre yeniden çalıştırmak** önce yarım işlemi kurtarır. Eski kurulumun yedeği korunur; işlem sonrasında dışarıdan değiştirilmiş klasörlerin üzerine yazılmaz. Bu kurtarma yeni sürümün oluşturduğu işlem kayıtları için geçerlidir.

Windows kullanıcı ve oyun klasörü adlarındaki Unicode karakterler ile `%` işareti ayarlarda korunur. Ayar değişiklikleri birlikte çalışan OKDEV süreçleri arasında sıraya alınır. Kalıcı dosya kilidinde eski ayar dosyası korunur; bozuk bir dosya tek ayarla yeniden oluşturulmaz.

Mod Merkezi ve rehber, Microsoft Edge WebView2 Runtime kullanır. Bileşen bulunamazsa Mod Merkezi boş pencere yerine kurulum açıklaması gösterir; yalnızca kullanıcı seçerse [Microsoft’un resmi indirme sayfasını](https://developer.microsoft.com/en-us/microsoft-edge/webview2/) açar. Uygulama bu bileşeni kendiliğinden indirmez veya kurmaz. Sistem durumu kurulu Runtime sürümünü gösterir.

**Sistem durumu → Depolama kullanımı** mod dosyaları, yerel yedekler, geçici indirmeler ve önbellekleri ayrı gösterir. Dosyalar silinmez. Büyük veya erişilemeyen klasörler süre/dosya sınırıyla taranır; eksik ölçümler “En az” olarak belirtilir. Tek düğmeyle yedek listesine gidilebilir.

Ek kontroller:

```powershell
python -m unittest discover -v
node test/professional_dom.cjs
python scripts/check_hub_endurance.py --duration 3600 --interval 15
python scripts/check_hub_webview.py --soak-seconds 10800
python scripts/check_hub_webview.py --zoom-check --accessibility --capture
python scripts/check_library_model.py --duration 5400 --interval 0.5
```

Dayanıklılık kontrolü geçici kullanıcı verisi ve yalnızca `127.0.0.1` test sunucusu kullanır. İndirme hatası/yeniden deneme, seçim geri alma, profil, kaldırma ve geri yükleme döngülerini; bellek, iş parçacığı ve açık dosya sayısını kaydeder. Sonuçlar ve sınanan kaynakların SHA-256 değerleri `build/hub-endurance.json` dosyasındadır. Oyun içi uyumluluk kontrolünün yerini almaz.

## 1.4.0: Yeni Mod Merkezi ve oyun rehberi

Yeni masaüstü arayüzünde Genel bakış, Keşfet, Modlarım, Oyun rehberi, Profiller, Ayarlar ve Sistem durumu ayrı bölümlerdir. Koyu/açık/sistem teması, kompakt kartlar, azaltılmış hareket, klavyeyle arama ve küçük pencere düzeni bulunur. Mod detayları ayrı açılır; ana ekran günlük kullanım için sade tutulur.

RuneForge seçkisinde yapımcı, lisans ve özgün önizlemeleriyle 32 içerik vardır: şampiyon görünümleri, HUD/arayüz, yazı tipi, harita ve spiker paketleri. **Kütüphaneme ekle** özgün RuneForge CDN dosyasını indirir; SHA-256 ve arşiv doğrulamasından sonra kapalı olarak ekler. Dosya doğrulanan sürümden farklıysa yüklenmez. Paketler uygulama kurulumuna dahil değildir. Kaynak sayfalarındaki yama ve özel kullanım notları geçerlidir.

**Oyun rehberi** isteğe bağlıdır ve varsayılan olarak kapalıdır. Etkinleştirildiğinde kendi şampiyonun kilitlenince doğru Mobalytics build sayfası hazırlanır. Varsayılan olarak kilitlemede gösterilir; oyun başlarken gizlenir. Oyunda **Ctrl+Shift+B** ile açılıp kapanır; kısayol ve panelin tarafı değiştirilebilir. İstemci içindeki küçük Mobalytics menüsünden de açılıp kapatılır. Seçim üzerinde gezinmek veya takım arkadaşının kilitlemesi rehber açmaz; takas edilen şampiyon takip edilir. ARAM seçimleri doğrudan ARAM build sayfasına gider. Otomatik gösterim klavye odağını değiştirmez. Oyun üstünde görünmesi için pencereli veya kenarlıksız ekran modu kullanılmalıdır.

Rehber, Mobalytics'in güncel web sayfasını ayrı bir pencerede gösterir. Rünler, Eşyalar ve Yetenek düğmeleri sayfanın ilgili bölümlerine gider. Uzaktaki sayfaya OKDEV'in dosya/işlem API'si verilmez. Otomatik rün aktarımı veya tam ekran oyuna enjekte edilen overlay değildir.

### Günlük kullanım

1. **Keşfet** bölümünde mod, şampiyon veya yapımcı ara; kategori ve favori filtrelerini kullan.
2. Bir içerikte **Kütüphaneme ekle** seç. Yerel `.fantome`/`.zip` dosyaları için **Mod ekle** kullan; paket bilgileri otomatik algılanır.
3. **Modlarım** bölümünden istediğin modları etkinleştir. Şampiyon başına ve HUD, harita, yazı tipi, spiker kategorilerinin her birinde tek seçim uygulanır. Değişiklikler sonraki oyun hazırlanırken kullanılır.
4. **Profiller** altında etkin kombinasyonunu kaydet; daha sonra uygula, adını değiştir veya mevcut seçimlerle güncelle.
5. Kaldırılan modları ve eski sürümleri **Modlarım → Kaldırılan modlar ve sürüm yedekleri** bölümünden geri yükle. Geri yüklenen mod kapalıdır.
6. **Oyun rehberi** bölümünden Mobalytics'i etkinleştir. İstersen şampiyon ve rol seçerek maç dışında da rehber aç.
7. Sorun yaşarsan **Sistem durumu** kontrolünü çalıştır. Destek raporu hesap bilgisi, erişim anahtarı veya ham günlük içermez; yalnızca sen kaydedip paylaşırsan gönderilir.

### Doğrulama ve sınırlar

Birim ve DOM testleri, gerçek WebView2 arayüzü, özgün CDN'den indirme, Mobalytics sayfasının yüklenmesi ve paketlenmiş arka uç ayrı test edilir. Seçki paketleri arşiv bütünlüğü ve uygulamanın kullandığı dosya çıkarma yolu ile kontrol edilir. Kurulu oyun verileriyle geçici overlay oluşturma ayrıca, oyun veya patcher çalıştırılmadan sınanabilir. Bu kontroller canlı maç uyumluluğunun yerine geçmez; şampiyon kilitleme ve maç evreleri ayrıca kayıtlı test senaryolarıyla sınanır.

```powershell
python -m unittest discover -s hub/tests -v
npm ci --prefix test/ui --ignore-scripts --no-audit --no-fund
node test/hub_view.cjs
node test/hub_dom.cjs
node test/guide_plugin.cjs
python scripts/check_hub_webview.py --capture
python scripts/check_guide_companion.py
python scripts/check_curated_download.py
python scripts/check_release_candidate.py --with-ui
```

WebView kontrolleri pencere açar; oyun sırasında çalıştırılmamalıdır. Paket denetimi gerçek kullanıcı verisine dokunmadan, dağıtılan kodla aynı derlenmiş Python içeriğini taşıyan geçici bir EXE kopyasını sınar. Kontrol raporları `build/` altında tutulur ve kurulum paketine girmez.

## 1.2.1 güncelleme düzeltmesi

Eski güncelleyicide takılan mevcut kullanıcılar için `OKDEV_Repair_1.2.1.exe` ayrıca dağıtılır. League kapalıyken çalıştırılıp **Onar ve 1.2.1’e geçir** seçilir. Varsayılan kullanıcı kurulumu otomatik bulunur; özel konum elle seçilebilir. Onarım seçilen kurulumun OKDEV işlemlerini kapatır, paketin SHA-256 değerini denetler ve mevcut LTK/ayarları koruyarak yedekli geçiş yapar. Yeni kurulumlar için Setup kullanılmalıdır. Araç `scripts/build_public_repair.py` ile oluşturulur; 1.2.1'den yeni sürümleri geri almaz.

Güncelleyici, kapanan uygulama işlemlerini bekler ve kalan işlemleri ad/PID ile bildirir. Başlatıcı güncelleyiciyi kurulum klasörünün dışında çalıştırır; Windows çalışma dizini kilidi önlenir. Sonraki güncellemelerde doğrulanmış paketteki güncel yardımcı kullanılır. İlgili 29 test, kurulum açılışı ve ayrı test kurulumunda derlenmiş güncelleyicinin uçtan uca akışı doğrulandı.

Eski sürümler 1.2.1'e geçerken hâlâ eski yardımcılarını kullanır. League ve sistem tepsisindeki OKDEV tamamen kapatılmalıdır. Eski güncelleyici yine takılırsa `OKDEV_Setup_1.2.1.exe` mevcut klasöre bir kez uygulanabilir; kullanıcı verileri korunur. Sürüm kanalı: https://github.com/okdev01/OKDEV/releases/latest

## 1.2.0: Mod Merkezi

Bu sürüm https://github.com/okdev01/OKDEV/releases/tag/v1.2.0 adresinde kararlı güncelleme olarak yayımlandı. Uygulamanın kullandığı latest uç noktası ve herkese açık güncelleme ZIP'inin SHA-256 değeri doğrulandı. Yayımlama sırasında bu bilgisayardaki kurulum ve açık oyun değiştirilmedi.

- Ayrı masaüstü penceresinde mod kütüphanesi, indirilen modlar, yardımcılar, Mobalytics ve yayımlama ekranları bulunur. Sistem tepsisinden yeniden açılabilir.
- Katalog başlangıçta boştur: `mods/catalog.json`. Hazır mod dosyası bulunmadığından örnek içerik yayımlanmaz. `.fantome`/`.zip` paketleri yerelden eklenebilir; indirilen paketler SHA-256 ve arşiv denetiminden geçer. Şampiyon başına bir mod etkinleştirilir.
- Yayımlama ekranı GitHub deposunda Contents yazma yetkili erişim anahtarı gerektirir. Anahtar diske kaydedilmez. Mod sürümleri ön sürüm olarak yayımlanır ve uygulamanın kararlı güncelleme kanalını değiştirmez.
- Otomatik maç kabulü varsayılan olarak kapalıdır; Yardımcılar ekranından açılır ve tercih saklanır.
- Mobalytics kendi web sayfası olarak ayrı uygulama penceresinde açılır. Bu pencereye OKDEV dosya/işlem API'si verilmez. Mobalytics masaüstü overlay'i veya otomatik rün aktarımı bu entegrasyonun parçası değildir.
- Birim testleri, paketlenmiş WebView2 arayüzü ve Mobalytics sayfasının yüklenmesi doğrulandı. Gerçek modla oyun içi uygulama, parti ve canlı maç kabulü kullanıcı müsait olduğunda ayrıca sınanmalıdır.

## 1.1.0 geçiş sürümü

- Yeni OK monogramı: uygulama, kurulum, sistem tepsisi, yükleyici ve istemci menüsü.
- Kullanıcı verileri `%LOCALAPPDATA%\OKDEV` altında. İlk açılışta eski `Rose` klasöründen ayarlar, skinler, modlar, geçmiş, parti anahtarları ve eklenti tercihleri kopyalanır. Kaynak veriler silinmez. Var olan OKDEV verilerinin üzerine yazılmaz.
- Eklentiler `OKDEV-*` adını kullanır. Yeni parti kodları `OKDEV:` ile başlar; eski `ROSE:` kodları da kabul edilir. Relay uyumluluk sürümü korunur.
- `core.dll`, Pengu Loader v1.1.6 açık kaynak kodundan, sabitlenmiş CEF 108 başlıklarıyla derlenir. OKDEV yapılandırmasını okur; Rose DLL'si kullanılmaz.
- Uygulama açılışında yalnızca `okdev01/OKDEV` deposunun kararlı sürümleri kontrol edilir. Onaylanan paket SHA-256 ile doğrulanır; mevcut kurulum yedeklenerek değiştirilir. Dosya değişimi başarısız olursa eski kurulum geri konur. Oyun istemcisi açıkken güncelleme uygulanmaz.
- İnternet veya güncelleme hatası mevcut uygulamanın açılmasını engellemez. Telemetri kapalıdır.

## Kurulum ve geçiş

[Güncel sürümün](https://github.com/okdev01/OKDEV/releases/latest) `OKDEV_Setup_<sürüm>.exe` dosyasını indirin. League ve sistem tepsisindeki OKDEV kapalıyken mevcut OKDEV kurulum klasörünü veya yeni bir klasörü seçin. Setup geçerli mevcut kurulumu yedekleyerek günceller. ZIP güncelleme paketi otomatik başlatıcı içindir; yeni kurulum için Setup kullanın. LTK patcher dosyaları kullanıcı tarafından sağlanır ve pakette dağıtılmaz.

Yeni çekirdeğin gerçek League istemcisinde, antrenman oyununda ve iki oyunculu parti oturumunda doğrulanması gerekir. Birim testleri ve DLL derleme kontrolleri gerçek oyun doğrulamasının yerini tutmaz.

## Derleme

Python 3.12, Node.js 22+, Visual Studio 2022 C++ araçları, Windows SDK ve .NET Framework 4.7.2 hedefleme paketi gerekir.

```powershell
python -m pip install --require-hashes -r requirements-windows.lock
python scripts/build_brand_assets.py
python scripts/build_pyinstaller.py
python scripts/build_okdev_setup.py
python scripts/create_update_package.py
```

`dist/OKDEV` uygulamayı ve bağımsız güncelleme yardımcısını içerir. `release/` altında kurulum, güncelleme ZIP'i ve SHA-256 dosyaları oluşur. GitHub Actions aynı derlemeyi ve testleri çalıştırır; otomatik yayımlama yapmaz.

## Yeni sürüm yayımlama

1. `config.py`, `setup_app/setup.py`, `okdev_version.txt` ve `installer.iss` sürümlerini birlikte artırın.
2. Yukarıdaki derleme ve testleri çalıştırın; adayı gerçek istemcide doğrulayın.
3. `okdev01/OKDEV` Releases altında aynı sürüm etiketiyle kararlı sürüm oluşturun.
4. `OKDEV_Setup_<sürüm>.exe`, `OKDEV_Update_<sürüm>.zip` ve `OKDEV_Update_<sürüm>.zip.sha256` dosyalarını yükleyin. Kaynak kod ZIP'i güncelleme paketi değildir.

1.1.2 sürümü https://github.com/okdev01/OKDEV/releases/tag/v1.1.2 adresinde yayımlandı; uygulamanın güncelleme adresi ve indirilen ZIP SHA-256 değeri doğrulandı. SHA-256 indirme bütünlüğünü doğrular; kod imzası değildir. Önceki kurulum, kurulum klasörünün yanındaki `.backup-*` klasöründe tutulur.

## Parti ve dış veri kaynakları

Parti sunucusu `wss://okdev.tr:9443`. `OKDEV_RELAY_URL` ile değiştirilebilir; eski `ROSE_RELAY_URL` değişkeni geçiş uyumluluğu için kabul edilir. İki oyuncunun da aynı relay ve parti bağlantısını kullanması gerekir. Özel mod dosyaları relay üzerinden aktarılmaz.

Parti açık/kapalı tercihi ve eklenen arkadaşlar hesap ve sunucu başına `party_sessions.json` içinde saklanır. İstemciye girişten sonra bağlantılar yeniden kurulur; geçici bağlantı hatalarında kayıt silinmez. Parti modunu düğmeyle kapatmak otomatik açılışı durdurur. Kendi seçiminiz ve arkadaşlarınızın skin adları istemcinin skin kataloğundan gösterilir. Kai’Sa 145999 ve diğer uzak form ID’leri parti paylaşımında korunur.

Bilinen açık sorun: Immortalized Legend Tristana (18080) ve Kai’Sa’nın gold eşiğinde otomatik form değiştirmesi oyun içinde henüz doğrulanmadı ve bu sürümde çözülmüş olarak sunulmuyor. Mevcut paketler yerel skin dosyalarını değiştirir; uygulamada gold eşiğini izleyip oyun içi form değiştiren bir mekanizma yoktur. Kai’Sa form seçimi/paylaşımı düzeltmesi otomatik gold dönüşümü düzeltmesi değildir.

Oyun içerikleri için mevcut LeagueSkins, darkseal ve CommunityDragon kaynakları dış bağımlılıktır. Bu veri depoları OKDEV'e aitmiş gibi gösterilmez; uygulama güncellemeleriyle aynı kanal değildir. Pengu Loader ve LTK bağımlılıkları devam eder.

## Lisans

Özgün uygulama: [Alban1911/Rose](https://github.com/Alban1911/Rose), Copyright (c) 2026 Alban and Florent, MIT. [Pengu Loader](https://github.com/PenguLoader/PenguLoader) açık kaynak çekirdeği ve yükleyicisi MIT lisansıyla kullanılır. Özgün lisanslar ve yazar atıfları korunur. OKDEV, Riot Games tarafından onaylanmış bir proje değildir.
