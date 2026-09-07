![skillstate-kit — Oturumlar arasında kalıcı görev durumu](assets/logo.svg)

# Türkçe başlangıç

[PyPI paketi](https://pypi.org/project/skillstate-kit/) · [Çalışan Python örneği](../README.md#python-integration) · [Kabul testleri](host-acceptance.md)

skillstate-kit, AI agent'lar için taşınabilir bir görev yürütme durumu katmanıdır. İlerleme, kanıtlar ve işlem durumu konuşma geçmişinden ayrı saklanır. Python, CLI ve MCP aynı çekirdeği kullanır; özel bir Python agent yazmanız gerekmez. MIT lisansıyla açık kaynak olarak yayımlanır. Sürüm alpha durumundadır.

**Dış proje doğrulaması:** Hugging Face smolagents'ın mevcut SQL agent'ı, 1.000 sentetik kayıt üzerindeki beş kontrolde entegrasyon öncesi ve sonrası aynı doğru sonuçları üretti. Skillstate ile çalışan süreç zorla kapatıldıktan sonra yeni süreç kalan iki sorguyla tamamlandı; bitmiş sorgular tekrarlanmadı. [Deneyin kapsamı, sonuçları ve tekrar çalıştırma adımları](smolagents-acceptance.md).

## Kurulum

Python 3.11 veya üzeri bir ortamda:

```text
python -m pip install "skillstate-kit[mcp]"
```

Ardından kullanacağınız projenin klasöründe:

```text
skillstate init
skillstate doctor --mcp
```

0.2.0 ile `init`, algılanan proje ortamlarını seçer ve MCP kuruluysa yapılandırır. `skillstate hosts detect` seçim gerekçelerini gösterir. Yalnızca `pip install skillstate-kit` de yeterlidir: temel paket CLI üzerinden çalışır. Belirli bir ortam için `skillstate init --host codex --mcp` kullanabilirsiniz. MCP ayarları bu makineye ait Python/proje yollarını içerir.

Agent oturumunu yeniledikten sonra normal görevinizi verin: “Bu projeye JWT doğrulaması ekle ve testlerini çalıştır.” Kurulan yönergeler agent'ı mevcut görevi bulmaya, uygun kaydı sürdürmeye ve kanıtlı adımlar kaydetmeye yönlendirir. Host'un yönergeleri izlemesi gerekir; paket her araç çağrısını zorla denetlemez.

`skillstate run find` ile kayıtları, `skillstate run context RUN_ID` ile güncel durumu görebilirsiniz. Tamamlanan adımı yeniden kaydetmek açık bir yeniden doğrulama gerekçesi ister. Kaynak dosyası değişirse yalnızca o dosyaya bağlı kanıtlar eski olarak işaretlenir. [Durum ve doğrulama sözleşmesi](execution-state.md).

**Ölçüm:** Yeni [kodlama deneyi](benchmarks/coding-agent.md) gerçek token ve süreyi ayrı raporlar. Kalıcı durumun çalışması otomatik maliyet tasarrufu anlamına gelmez; host'un konuşma geçmişini bu paket silemez.

## Otomatik üretim

Claude Desktop'ın **Chat** bölümünü kullanıyorsanız ayrıca `skillstate connect claude-desktop` çalıştırıp uygulamadan tamamen çıkın ve yeniden açın. Bu bağlantı Claude Code kurulumundan ayrıdır. Araç izinlerini uygulama içinde siz verirsiniz. `skillstate disconnect claude-desktop` bağlantıyı kaldırır, görev durumunu korur. Windows Store sürümü de desteklenir; birden fazla ayar dosyası bulunursa `--config DOSYA` ile seçilir.

Gerçek uygulama testlerinin sonucu [kabul raporunda](host-acceptance.md), tekrar edilebilir örnek ise [örnek projede](../examples/desktop_acceptance/README.md). Codex'te gerçek MCP üretimi ve ayrı oturumdan devam etme; ayrıca Codex → Claude Desktop Chat devri ve ikinci incelemeyle tamamlama doğrulandı. Claude Code için canlı uygulama testi yapılmadı.

Kurulumdan sonra agent'a “Generate skill state; bu skill'i durum yapısına dönüştür” diyebilirsiniz. Üretici kaynak envanterini hazırlayıp agent'ın önerdiği şemayı doğrular.

Doğrudan `generate`, yönergeleri koruyan sınırlı bir genel ilerleme şeması oluşturur. Alana özel dönüşüm için agent destekli `--prepare`/`--proposal` akışı veya yapılandırılmış `--base-url`/`--model` kullanılır. Terminal, IDE model hesabını otomatik kullanmaz.

## Çalıştırma ve devam

Üretim komutu görevi çalıştırmaz. Agent'a “qa-state skill'ini bu görevde kullan, ilerlemeyi ve kanıtları kaydet” diyerek çalışmayı başlatın. Durumu terminalden incelemek için:

```text
skillstate run open qa-state --owner codex --id qa-001
skillstate run context qa-001
skillstate run events qa-001
skillstate status
```

Her yeni görev için farklı bir run ID kullanın. Var olan göreve devam ederken yeniden açmak yerine mevcut durumu okuyun. Python ile doğrudan kullanım için [kopyalanıp çalıştırılabilen örneğe](../README.md#python-integration) bakın.

Üretilen skill, state açma, okuma, güncelleme, işlem sonucu kaydetme ve ortamlar arasında devretme adımlarını içerir. Python projeleri `SkillRuntime` ile bütün model/araç döngüsünü yönetebilir.

Native skill host'un konuşma geçmişini silmez. Makaledeki geçmiş taşımayan model girdisini kurmak için stateless adapter ile managed runtime kullanın.

`pending` veya `unknown` bir dış işlemin sonucunun belirsiz olduğunu gösterir. Tekrarlamadan önce dış sistemden sonucu kontrol edin ve açıkça uzlaştırın. Checkpoint dış dünyadaki işlemi geri almaz.

## Doğrulama

`skillstate demo` model hesabı gerektirmeyen kontrollü örnektir. `doctor --mcp` gerçek yerel MCP bağlantısı kurar. Bunlar bütün IDE sürümlerinin davranışını veya makalenin performans sonuçlarını doğrulamaz.

Ayrıntılar: [CLI](cli.md), [mimari](architecture.md), [ortam desteği](compatibility.md), [test matrisi](validation.md).
