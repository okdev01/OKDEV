# 26.22 kostüm paketi doğrulaması

Kaynak oyun verisi: kurulu League 26.22 arşivleri (yalnızca okundu).
Kostüm kapsamı Riot 26.22 notları ve istemcinin şampiyon kataloglarıyla karşılaştırıldı.

- Resmî yama notları: https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-22-notes/
- LTK sürümü: https://github.com/LeagueToolkit/ltk-manager/releases/tag/v1.33.0
- İngilizce kataloglar: CommunityDragon `latest/plugins/rcp-be-lol-game-data/global/default/v1/champions/{id}.json`
- Türkçe kataloglar: kurulu League istemcisinin `/lol-game-data/assets/v1/champions/{id}.json` yanıtları.

Paketler 103097, 28065, 28066, 145083, 84102, 96065 temel kostümlerini ve katalogdaki 23 rengini; ayrıca 79049 Gragas rengini kapsar. Toplam 30 paket, önceki ek pakete göre 28 yeni dosya ve 2 SHA-256 ile sınırlı yenilemedir.

PROP v3 kayıt sınırları ve bağlantıları `scripts/skin_bin_patch.py` ile okunur. SkinCharacterDataProperties ve ResourceResolver kayıtları seçilir; yalnızca kayıt kimliği temel kostüm yuvasına çevrilir. Alan yükleri aynen korunur, hedef kostüm BIN dosyası bağlantı olarak eklenir. Eski alan ayrıştırıcısı yeni oyun verisinde geçersiz tür hatası verdiği için kullanılmaz. Kaynak/yeniden yazım eşitliği ve yeni alanların korunması test edilmiştir.

30 paketin her biri mod-tools ile dışa aktarıldı, ZIP CRC ve paketlenmiş BIN eşitliği kontrol edildi, tekrar içe aktarıldı ve güncel oyun arşivleriyle ayrı overlay derlendi. Doğrudan BIN bağımlılıklarının varlığı ve kaynak oyun arşivlerinin boyut/değiştirme zamanının değişmediği kontrol edildi. Paket SHA-256 değerleri `assets/skin-patches/26.22/manifest.json` içindedir.

Yeni kurulum ve 26.20 ek paketinden yükseltme geçici kullanıcı klasöründe doğrulandı. Aynı işlem ikinci kez çalıştırıldığında dosya değişmedi. Bilinmeyen kullanıcı/kaynak paketleri korunur. Kostüm isimleri eksik kayıtlara eklenir.

Oyun içi görsel/ses doğrulaması yapılmadı. Çevrimdışı derleme ve LTK imza/derleme uyumluluğu bu doğrulamanın yerine geçmez.
