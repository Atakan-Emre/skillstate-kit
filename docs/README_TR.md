# Türkçe başlangıç

skillstate-kit, mevcut agent skill'lerini kalıcı ve doğrulanan görev durumuyla kullanmanızı sağlar. İlk sürüm alpha durumundadır; repo private, PyPI yayını henüz yapılmadı.

## Kurulum

Repo erişiminiz varsa:

```text
git clone https://github.com/Atakan-Emre/skillstate-kit.git
cd skillstate-kit
python -m pip install ".[mcp,http]"
```

Ardından kullanacağınız projenin klasöründe:

```text
skillstate init --host codex --host claude-code --host antigravity --mcp
skillstate generate skills/qa/SKILL.md --install
skillstate validate qa-state
skillstate doctor --mcp
```

`skills/qa/SKILL.md` yerine kendi dosyanızı kullanın. Yalnızca kullandığınız host'ları seçebilirsiniz. `--mcp` opsiyoneldir; temel kullanım CLI üzerinden çalışır. MCP ayarları bu makineye ait Python/proje yollarını içerir.

## Otomatik üretim

Kurulumdan sonra agent'a “Generate skill state; bu skill'i durum yapısına dönüştür” diyebilirsiniz. Üretici kaynak envanterini hazırlayıp agent'ın önerdiği şemayı doğrular.

Doğrudan `generate`, yönergeleri koruyan sınırlı bir genel ilerleme şeması oluşturur. Alana özel dönüşüm için agent destekli `--prepare`/`--proposal` akışı veya yapılandırılmış `--base-url`/`--model` kullanılır. Terminal, IDE model hesabını otomatik kullanmaz.

## Çalıştırma ve devam

Üretilen skill, state açma, okuma, güncelleme, işlem sonucu kaydetme ve ortamlar arasında devretme adımlarını içerir. Python projeleri `SkillRuntime` ile bütün model/araç döngüsünü yönetebilir.

Native skill host'un konuşma geçmişini silmez. Makaledeki geçmiş taşımayan model girdisini kurmak için stateless adapter ile managed runtime kullanın.

`pending` veya `unknown` bir dış işlemin sonucunun belirsiz olduğunu gösterir. Tekrarlamadan önce dış sistemden sonucu kontrol edin ve açıkça uzlaştırın. Checkpoint dış dünyadaki işlemi geri almaz.

## Doğrulama

`skillstate demo` model hesabı gerektirmeyen kontrollü örnektir. `doctor --mcp` gerçek yerel MCP bağlantısı kurar. Bunlar bütün IDE sürümlerinin davranışını veya makalenin performans sonuçlarını doğrulamaz.

Ayrıntılar: [CLI](cli.md), [mimari](architecture.md), [ortam desteği](compatibility.md), [test matrisi](validation.md).
