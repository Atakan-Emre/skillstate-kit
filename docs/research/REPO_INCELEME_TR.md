# skill-state-minimal: kod incelemesi ve deney sonuçları

İnceleme tarihi: 6 Eylül 2026.
Repo: https://github.com/kissishka/skill-state-minimal
İncelenen commit: `fdbb1cefc8078a1b12489fe47fb96b1d46190d6d`.
Yerel kopya: `research/skill-state-minimal`. Kaynak repo değiştirilmedi.

## Sonuç

Bu repo sade bir yürütme çekirdeği için yararlı bir referans. Kullanıcının hedeflediği otomatik skill dönüştürme ve çoklu geliştirme ortamı ürünü için doğrudan yeterli değil. Bu bir ürün kusuru olarak sunulmamalı: proje kendisini bilerek minimal ve bağımsız bir uygulama olarak tanımlıyor. [Repo README](https://github.com/kissishka/skill-state-minimal/tree/fdbb1cefc8078a1b12489fe47fb96b1d46190d6d)

Python 3.12.7 ve jsonschema 4.26.0 ile mevcut 31 testin tamamı geçti. Ek beş davranış kontrolü de aşağıdaki bulguları doğruladı. Bunlar sahte model/araç fonksiyonlarıyla yapılan yerel testlerdir; gerçek LLM başarısı veya üretim ortamı dayanıklılığı ölçülmedi. Kilit dosyasındaki ortam birebir yeniden kurulmadı.

## Gerçek yapı

| Dosya | Sorumluluk |
|---|---|
| `src/skill_state/runtime.py` | JSON normalizasyonu, şema doğrulama, merge patch, model/araç adımı, dosya kaydı |
| `src/skill_state/demo.py` | Önceden belirlenmiş model cevaplarıyla depo demosu |
| `tests/test_runtime.py` | Durum, JSON, araç ve kayıt sözleşmeleri |
| `tests/test_demo.py` | Demonun beklenen çıktıları |
| `pyproject.toml` | Python paketi ve `skill-state-demo` giriş noktası |
| `.github/workflows/ci.yml` | Ubuntu üzerinde Python 3.11–3.13 test ve build matrisi |

İncelenen kaynaklarda proje tarayıcısı, skill derleyicisi, MCP sunucusu, host kurucuları veya `generate` komutu bulunmuyor. [Paket tanımı](https://github.com/kissishka/skill-state-minimal/blob/fdbb1cefc8078a1b12489fe47fb96b1d46190d6d/pyproject.toml)

## Korunmaya değer tercihler

- State erişimi kopya döndürüyor; dışarıdan yanlışlıkla mutasyon sınırlandırılıyor.
- Aday değişiklik önce kopyaya uygulanıyor, tüm aday şema doğrulamasından geçiyor.
- Araç adları izin listesiyle kontrol ediliyor.
- NaN/Infinity, döngülü nesneler, sorunlu Unicode ve bazı Python alt sınıf davranışları reddediliyor.
- Başarısız ExecutionResult, önerilen state'in kaydedilmesini engelliyor.
- Dosya kaydı geçici dosya ve atomik değiştirme kullanıyor; geçmiş kayıtları prompt'a katılmıyor.

Bunlar [runtime.py](https://github.com/kissishka/skill-state-minimal/blob/fdbb1cefc8078a1b12489fe47fb96b1d46190d6d/src/skill_state/runtime.py) ve [testlerde](https://github.com/kissishka/skill-state-minimal/blob/fdbb1cefc8078a1b12489fe47fb96b1d46190d6d/tests/test_runtime.py) doğrulandı. Bu kontroller iş kurallarının doğruluğunu veya dış API işleminin tek sefer çalışmasını tek başına sağlamıyor.

## Ek deneylerle doğrulanan beş sınır

### 1. Yeniden denemede ilk gözlem kayboluyor

`step()` içindeki yeniden deneme, gözlemi yalnızca validation_error ile değiştiriyor. İlk istekteki benzersiz request_id ikinci prompt'ta bulunmadı. Referans test de bu davranışı bilinçli olarak bekliyor.

Etkisi: Model reddedilen öneriyi düzeltirken hangi öğe veya istek için işlem yaptığını kaybedebilir. Bizim tasarımımızda son görev gözlemi korunmalı, doğrulama hatası ayrı ve sınırlı bir feedback alanı olmalı. İlgisiz eski konuşmaların geri getirilmesi gerekmez.

Kaynak: [runtime.py:293](https://github.com/kissishka/skill-state-minimal/blob/fdbb1cefc8078a1b12489fe47fb96b1d46190d6d/src/skill_state/runtime.py#L293).

### 2. Araçlara özel argüman şeması yok

`arguments` alanının nesne olması kontrol ediliyor. `quantity="not-an-integer"` değeri sahte executor'a ulaştı. Bu, uygulamanın executor içinde yapabileceği ek kontrolü dışlamaz; çekirdeğin kendisi araç başına tip ve sınır doğrulaması sağlamıyor.

Bizim ToolSpec yapımız input_schema, timeout, yan etki sınıfı, sonuç doğrulayıcı ve isteğe bağlı idempotency desteği taşımalı.

Kaynak: [runtime.py:366](https://github.com/kissishka/skill-state-minimal/blob/fdbb1cefc8078a1b12489fe47fb96b1d46190d6d/src/skill_state/runtime.py#L366).

### 3. Audit hatası, başarılı state kaydından sonra dışarı fırlıyor

Audit yazma fonksiyonuna hata enjekte edildi. `step()` hata verdi; fakat bellekte ve dosyada count=1 olarak kaydedilmişti. Çağıran uygulama bütün adımı tekrar ederse araç işlemini yeniden çalıştırabilir.

Bizde operation kaydı, domain state, checkpoint ve yerel audit olayı aynı SQLite transaction içinde sonuçlandırılmalı. Harici audit sistemine gönderim ayrı outbox üzerinden yapılabilir. Dış API ile SQLite arasında atomiklik iddia edilmemeli.

Kaynak: [runtime.py:313](https://github.com/kissishka/skill-state-minimal/blob/fdbb1cefc8078a1b12489fe47fb96b1d46190d6d/src/skill_state/runtime.py#L313).

### 4. Executor istisnasından önce kalıcı işlem niyeti kaydedilmiyor

Sahte araç yan etkiyi gerçekleştirdikten sonra TimeoutError üretti. Kalıcı pending operation/audit kaydı oluşmadı. Durum eski kaldı, ama dış dünyanın da eski kaldığı sonucunu çıkaramayız.

Bizim akışımız pending → succeeded/failed/unknown olmalı. Unknown durum yeniden çalıştırma izni sayılmamalı; sonuç sorgulama veya uygulamaya özgü kurtarma politikası gerekir.

Kaynak: [runtime.py:299](https://github.com/kissishka/skill-state-minimal/blob/fdbb1cefc8078a1b12489fe47fb96b1d46190d6d/src/skill_state/runtime.py#L299).

### 5. Bağlam için sert büyüklük sınırı yok

Bir milyon karakterlik gözlem kabul edildi ve 1.000.045 baytlık prompt oluştu. `prompt_size`, token değil UTF-8 bayt sayısıdır. Sabit alan isimleri bağlamın sabit boyutta kalmasını garanti etmiyor.

Bizde durum, gözlem, artifact okuması ve model çıktısının ayrı bütçeleri olmalı. Karakter, bayt, tahmini token ve sağlayıcının bildirdiği gerçek token ölçümleri farklı isimlerle tutulmalı.

Kaynak: [runtime.py:216](https://github.com/kissishka/skill-state-minimal/blob/fdbb1cefc8078a1b12489fe47fb96b1d46190d6d/src/skill_state/runtime.py#L216), [runtime.py:338](https://github.com/kissishka/skill-state-minimal/blob/fdbb1cefc8078a1b12489fe47fb96b1d46190d6d/src/skill_state/runtime.py#L338).

## Testlerin kanıtlamadığı konular

Gerçek modelle şema üretimi, araç sonuçlarının anlamsal doğruluğu, çok süreçli state çakışması, işlem sırasında süreç öldürülmesi, bütünleşik IDE kullanımı, ortamlar arası devir ve gerçek token tasarrufu bu testlerle doğrulanmış değildir. Yerel Windows testleri geçti; mevcut upstream CI dosyası Windows matrisi içermiyor.

## Bizim ürüne dönüşen gereksinimler

| İnceleme sonucu | Ürün gereksinimi |
|---|---|
| Model çağrısı yalnızca callback | Callback korunmalı; ayrıca host destekli üretim ve opsiyonel sağlayıcı adapter'ı |
| Şema elle hazırlanıyor | Kaynak kanıtlı otomatik şema/skill üretimi |
| Tek adım API | Run yaşam döngüsü, durma, devam etme, devir |
| Dosyada tek state | Run kimliği, revizyon, SQLite işlem günlüğü |
| İzin listesi yalnızca ad düzeyinde | Araç sözleşmesi ve argüman doğrulama |
| IDE bağlantıları yok | Skill + CLI + MCP + yeteneklere göre hook adapter'ları |
| Girdi sınırlandırılmıyor | Bütçe politikası ve taşan içeriğin kontrollü harici saklanması |
| Demo scripted | Gerçek host ve model testleri için ayrı doğrulama paketi |

## Tekrar üretme

Ek kontroller `research/probe_minimal.py` içinde; gözlenen sonuçlar `research/probe_results.json` dosyasında. Betik ağ veya gerçek model çağrısı yapmaz; geçici dosyalar ve sahte executor kullanır. Upstream kaynaklarını değiştirmez.

Bu inceleme bir fork veya kod aktarımı kararı değildir. Yeni ürünün modüler sözleşmelerle geliştirilmesi daha uygun görünüyor; referans uygulamanın küçük doğrulama yaklaşımı karşılaştırma noktası olarak kullanılabilir.
