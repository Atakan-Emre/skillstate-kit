# Python Skill State — kütüphane tasarım önerisi

Güncel kapsam notu: Sonraki kullanıcı isteğiyle otomatik skill üretimi ve Codex/Claude Code/Antigravity entegrasyonu ana kapsama alındı. Güncel ürün kararı [URUN_MIMARI_V2_TR.md](URUN_MIMARI_V2_TR.md), kod incelemesi [REPO_INCELEME_TR.md](REPO_INCELEME_TR.md) içindedir. Bu dosya ilk tasarımı korur; çelişen kapsam maddelerinde v2 belge esas alınır.

Durum: Mimari öneri; henüz uygulanmış veya test edilmiş bir Python paketi değildir.
İnceleme tarihi: 6 Eylül 2026.
Araştırma temeli: [SKILL.state v3](https://arxiv.org/html/2608.26263v3), Sanket Badhe, Priyanka Tiwari ve Jonghyun Chung. Aşağıdaki API, veri modeli ve çalışma garantileri bizim ürünleştirme önerimizdir; makalenin referans uygulaması değildir.

## Ürün amacı

Mevcut Python uygulamalarının model istemcisini, iş fonksiyonlarını ve dağıtım şeklini koruyarak görev durumunu yönetebilmesi. Entegrasyon bir model sağlayıcısına bağımlı olmamalı. İlk ürün tek çalışma üzerinde tek yazıcı varsaymalı; farklı run_id değerleri birbirinden bağımsız çalışabilmeli.

Kullanıcı dört şey sağlar: görev talimatı, alan şeması, mevcut model çağrısını saran fonksiyon, izin verilen araç fonksiyonları. İsteğe bağlı olarak mevcut veritabanını bağlar. Her projede sıfır ayarla doğru şema üretileceği vaat edilmez.

## Durum modelinin katmanları

1. SkillDefinition: skill_id, version, instructions, state_schema ve araç sözleşmeleri. Çalışma başladığında tanım sabitlenir; içerik özeti checkpoint içine yazılır.
2. DomainState: uygulamanın anlamlı görev bilgileri. Örneğin aktif test planı, mevcut hata, doğrulanmış test sonucu ve çıktı dosyası referansı.
3. RunMetadata: run_id, state_version, schema_version, status, step_count, bütçeler. Model bu alanları değiştiremez.
4. OperationRecord: operation_id, tool_name, arguments, expected_state_version, status ve sonuç referansı. Runtime sahipliğindedir.
5. ArtifactStore: büyük raporlar, dosyalar ve araç çıktıları. Model girdisine gerektiği kadar içerik aktarılır; referansın varlığı tek başına modelin içeriği bildiği anlamına gelmez.

DomainState içinde doğrulanmış gerçekler ile modelin hipotezleri ayrı tutulur. Her kritik sonuç için kaynağı ve ilgili nesnenin sürümünü saklamak gerekir. Örneğin test başarısı commit kimliğiyle ilişkilendirilir; başka commit için otomatik geçerli sayılmaz.

## Çekirdek bileşenler

| Bileşen | Sözleşme |
|---|---|
| Skill | Tanım ve şema sürümünü sabitler |
| ContextBuilder | Talimat, durum ve son gözlemden sınırlı model girdisi oluşturur |
| ModelAdapter | Projedeki mevcut çağrıyı kullanarak yapılandırılmış Decision döndürür |
| PatchEngine | Değişiklikleri kopyaya uygular, tamamını doğrular, sonra kaydeder |
| ToolRegistry | Araç adını kayıtlı Python fonksiyonuna ve argüman şemasına eşler |
| StateStore | Sürüme bağlı atomik kayıt ve checkpoint sağlar |
| Runtime | Adım döngüsünü, hata politikasını ve durma koşullarını yönetir |
| EventSink | İşlem sonucunu ve ölçümleri model bağlamı dışında kaydeder |

Modelden yalnızca karar sözleşmesi istenir; özel düşünce zincirinin açığa çıkarılması entegrasyon gereksinimi değildir. Model adapter'ı konuşma geçmişini veya sunucu tarafındaki eski konuşma oturumunu kendiliğinden eklememelidir.

## Değişiklik sözleşmesi

İlk API için açık set/delete işlemleri önerilir. Böylece bir alanı silmek ile değerini null yapmak farklı işlemlerdir. Yol gösterimi tek bir standarda bağlanmalı, iç içe nesnelerde davranış belgelenmelidir.

- Gönderilmeyen alan korunur.
- Listeler ilk sürümde bütün olarak değiştirilir; örtük birleştirme yapılmaz.
- Bilinmeyen yollar, korumalı alanlar ve geçersiz tipler reddedilir.
- Önce aday durum oluşturulur; tam şema ve iş kuralları doğrulanır.
- Tek bir işlem geçersizse bütün değişiklik reddedilir.
- expected_version tutmuyorsa eski karar güncel duruma uygulanmaz.

Makale biçimiyle uyum isteyen kullanıcılar için null-deletion davranışı ayrı ve açıkça adlandırılmış bir dönüştürücü olabilir. İki davranış aynı API içinde sessizce karıştırılmamalı.

## Araç çalıştırma ve kesinti davranışı

Modelin “işlem başarılı” demesi dış sistemin değiştiğinin kanıtı değildir. Önerilen akış:

1. Güncel checkpoint okunur; ilgili çalışma için sahiplik alınır.
2. Model kararı üretilir; durum değişikliği, araç argümanları ve iş kuralları doğrulanır.
3. İşlem niyeti kalıcı olarak pending kaydedilir. Henüz araç sonucu başarı sayılmaz.
4. Araç operation_id ile çağrılır. Dış sistem destekliyorsa bu değer idempotency anahtarı olarak kullanılır.
5. Doğrulanmış sonuç uygulamanın deterministik reducer fonksiyonuyla duruma işlenir. Sonuç ve checkpoint aynı yerel işlemde kaydedilir.
6. Zaman aşımı veya kesinti sonucu belirsizse status=unknown olur; yeniden denemeden önce dış sistem sorgulanır.

SQLite işlemi uzaktaki API ile tek bir dağıtık işlem oluşturmaz. Bu nedenle genel exactly-once garantisi verilmez. Kullanıcının araç sağlayıcısı idempotency veya sonuç sorgulama desteği sağlamalıdır; sağlayamıyorsa belirsiz işlem durdurulur.

Modelin gözlemden çıkardığı geçerli bilgilerle, henüz çalışmamış aracın beklenen sonuçları ayrı tutulmalı. Geçerli gözlem bilgileri araç başarısız diye kaybedilmemeli; başarısız araç için başarı bilgisi yazılmamalı.

## Entegrasyon yüzeyi

İki kullanım biçimi önerilir:

- Managed runtime: Kütüphane model ve araç döngüsünü işletir. Yeni küçük projeler için uygundur.
- Step API: Proje kendi döngüsünü korur; prepare, validate, commit_result adımlarını çağırır. Var olan agent sistemlerine geçiş için önceliklidir.

Önerilen, henüz çalıştırılabilir olmayan kullanım taslağı:

```python
runtime = SkillRuntime(
    skill=skill_definition,
    model=my_model_adapter,
    tools={"run_tests": run_tests, "read_report": read_report},
    store=SQLiteStateStore("skillstate.db"),
)

result = await runtime.run(
    run_id="qa-1042",
    initial_state=initial_state,
    observation={"event": "tests_requested", "target": "checkout"},
    max_steps=30,
)
```

Tekrar başlatma ayrı resume(run_id) metoduyla yapılmalı. Var olan run_id üzerine yeni initial_state yazılması hata olmalı. Yeniden başlatmada skill sürümü ve şema uyumu doğrulanmalı. Şema geçişi sessiz yapılmamalı.

## Bağlam ve depolama bütçeleri

State alan sayısına sınır koymak tek başına yeterli değildir. Bir string veya liste sınırsız büyüyebilir. Alan uzunlukları, koleksiyon boyutları, gözlem boyutu, toplam bağlam ve model çıkışı için ayrı sınırlar tanımlanmalı.

Bütçe aşımında önemli bilgileri sessiz kesmek yerine yapılandırılmış hata veya alanın kendi küçültme politikası uygulanmalı. Büyük sonuçlar ArtifactStore'a taşınabilir. Hangi parçanın tekrar okunacağı görev mantığına bağlıdır.

Token ölçümü model adapter'ından alınmalı; karakter sayısı token gibi raporlanmamalı. Provider gerçek kullanım bildirmiyorsa ölçümün tahmini olduğu belirtilmeli. Girdi, çıktı, retry, gecikme ve varsa cache ölçümleri ayrı saklanmalı.

## İlk sürüm kapsamı

Python 3.11+ hedefi, tip ipuçları, JSON Schema doğrulaması, async çekirdek, callback model adapter'ı, kayıtlı araçlar, MemoryStore ve SQLiteStore önerilir. Sağlayıcı SDK'ları çekirdek bağımlılık olmamalı. Paket ve import adı yayın öncesinde ayrıca kontrol edilmeli; bu belge PyPI adının boş olduğunu iddia etmez.

İlk somut demo kontrollü bir test yürütme görevi olabilir: planı al, testleri çalıştır, sonucu doğrula, rapor referansını kaydet. Kullanıcının gerçek projesine entegrasyon için o projenin kaynak kodu ve iş sözleşmesi ayrıca incelenir.

İlk sürüm dışında tutulacaklar: paylaşılan state'e çok ajanlı eşzamanlı yazma, otomatik şema keşfi, görsel iş akışı editörü ve çok sayıda hazır framework adapter'ı. Bunlar çekirdek garantiler kanıtlandıktan sonra eklenebilir.

## Kabul testleri

1. Geçersiz değişiklikten sonra durum ve sürüm aynı kalır.
2. Bir iç alan değişikliği diğer alanları kaybettirmez.
3. İki eski sürümlü kararın ikisi birden kaydedilemez.
4. Başarısız araç başarı olarak görünmez.
5. Araç çalıştıktan sonraki kesintide aynı yan etki körlemesine tekrarlanmaz.
6. Farklı run_id değerleri birbirinin verisini okuyamaz.
7. Artan adım sayısı, sabit görev verisinde modele eski konuşmaları eklemez.
8. Sınırdan büyük durum veya gözlem açık bütçe hatası üretir.
9. Checkpoint, doğru skill ve şema sürümüyle devam eder.
10. Sonuçsuz döngü max_steps, timeout veya uygulama bitirme koşuluyla durur.

Performans değerlendirmesinde aynı görevler ve model ayarlarıyla mevcut sistem ve yeni runtime karşılaştırılmalı. Başarı oranı, toplam gerçek token, p50/p95 gecikme, tekrar edilen araç çağrısı, yanlış durum güncellemesi ve kesintiden toparlanma ölçülmeli. Sadece kısa prompt üretmek ürün başarısı sayılmamalı.

## İncelenen bağımsız uygulama

[kissishka/skill-state-minimal](https://github.com/kissishka/skill-state-minimal) Python için bağımsız bir minimal uygulama sunuyor; README kapsamı deneylerin yeniden üretimi olarak tanımlamıyor. Bu incelemede kodu çalıştırılmadı veya kütüphanemize alınmadı. Yeniden kullanım kararı için kod, testler ve lisans ayrıca incelenmeli.
