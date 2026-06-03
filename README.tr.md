<p align="center">
  <img src="docs/images/logo.png" alt="ScribeFlow — Whisper transcription everywhere" width="520" />
</p>

<p align="center">
  <a href="README.md">English</a> | <strong>Türkçe</strong>
</p>

<p align="center">
  <strong>Ses ve video kayıtlarınızı — ders, röportaj, film — temiz metin transkriptlerine ve
  altyazı dosyalarına dönüştürün.</strong><br/>
  Kendi bilgisayarınızda çalışır (hiçbir şey buluta yüklenmez). Bir çalışma yarıda kesilirse,
  aynı komutu yeniden çalıştırın — tam kaldığı yerden devam eder.
</p>

<p align="center">
  <a href="https://pypi.org/project/scribeflow/"><img alt="PyPI" src="https://img.shields.io/pypi/v/scribeflow?style=flat-square&color=2F81F7" /></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-2F81F7?style=flat-square" />
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-Apache--2.0-7DCEA0?style=flat-square" /></a>
  <a href="https://github.com/htahaozlu/scribeflow/actions"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/htahaozlu/scribeflow/ci.yml?branch=main&style=flat-square&color=2F81F7" /></a>
  <a href="https://pypi.org/project/scribeflow/"><img alt="Downloads" src="https://img.shields.io/pypi/dm/scribeflow?style=flat-square&color=7DCEA0" /></a>
</p>

<p align="center">
  <img alt="Linux" src="https://img.shields.io/badge/Linux-destekli-2F81F7?style=flat-square&logo=linux&logoColor=white" />
  <img alt="macOS" src="https://img.shields.io/badge/macOS-Apple%20Silicon-2F81F7?style=flat-square&logo=apple&logoColor=white" />
  <img alt="Google Colab" src="https://img.shields.io/badge/Google%20Colab-hazır-7DCEA0?style=flat-square&logo=googlecolab&logoColor=white" />
</p>

<p align="center"><sub>OpenAI Whisper konuşma tanıma modelleriyle çalışır (faster-whisper · whisper.cpp · openai-whisper).</sub></p>

---

## 60 saniyede transcript

> **Python 3.10–3.12** ve bir terminal gerekir (macOS'ta Terminal, Windows'ta PowerShell).

```bash
pip install scribeflow
scribeflow transcribe ./ders.mp4
```

Bir de **ffmpeg** gerekir (tek seferlik) — `brew install ffmpeg` (macOS) ya da
`sudo apt-get install -y ffmpeg` (Linux). Kurulumunu kontrol için: `scribeflow doctor`.

**Sonuç:** transkript `scribeflow-output/ders/ders_transcript.txt` dosyasına yazılır.
Altyazı da ister misiniz? `--format srt` ekleyin:

```bash
scribeflow transcribe ./ders.mp4 --format srt
```

Çalışma durursa (çökme, kapanan dizüstü, kopan bağlantı) **aynı komutu** yeniden çalıştırın —
son biten parçadan devam eder; tekrar eden ya da bozuk metin olmaz.

---

## Neden ScribeFlow

Whisper'ı kendiniz çalıştırmakla aynı işi yapar, ama can sıkan kısımları halleder:

- 🛟 **Emeğiniz boşa gitmez.** İlerlemeyi parça parça kaydeder, her kesintiden sonra devam eder —
  var olma sebebi bu.
- 💻 **Her yerde çalışır.** Dizüstünüz (CPU ya da NVIDIA GPU), Mac (Apple Silicon / Metal) ya da
  **ücretsiz Google Colab** — donanımı algılar, uygun modeli otomatik seçer.
- 📥 **Her kaynaktan.** Bir dosya, bütün bir klasör, bir URL (ör. YouTube) ya da Google Drive.
- 📝 **Altyazı dahil.** Her zaman `.txt`; istenirse `.srt` / `.vtt` / `.json` — tüm kayıt boyunca
  doğru zaman kodlarıyla.
- 🔒 **Varsayılan olarak özel.** Her şey açık modellerle yerelde çalışır — hiçbir bulut servisine
  veri gönderilmez.

**Diller.** ScribeFlow, Whisper'ın desteklediği tüm dilleri işler. Varsayılanlar **Türkçe**'ye göre
ayarlıdır (`-l tr`); `-l en` (ya da başka kod) verin veya dili algılamak için `-l auto` kullanın.

**Doğruluk.** Transkriptler konuşma tanımayla otomatik üretilir — çok iyi ama kusursuz değil.
Özel adları, teknik terimleri ve üst üste binen konuşmaları gözden geçirmeyi planlayın. Resmî ya da
birebir kelimesi kelimesine bir kayıt değildir.

---

## Demo

<p align="center">
  <img src="docs/images/demo.gif" alt="ScribeFlow bir dersi deşifre ediyor, kesiliyor, sonra devam ediyor" width="760" />
</p>
<p align="center"><sub><em>Deşifreyi başlat, kes, aynı komutu yeniden çalıştır — kaldığı yerden devam edip bitirir.</em></sub></p>
<p align="center"><sub>Yeniden üret: <code>scripts/make-demo-gif.py</code> (her yerde çalışır) ya da <code>scripts/record-demo.sh</code> (gerçek kayıt, <a href="https://github.com/charmbracelet/vhs">vhs</a> gerekir).</sub></p>

---

## Kurulum

Temel kurulum küçüktür: motor + varsayılan **faster-whisper** arka ucu (CPU'da hazır çalışır).

```bash
pip install scribeflow
```

Tek sistem bağımlılığı **ffmpeg**:

```bash
brew install ffmpeg                  # macOS (Homebrew)
sudo apt-get install -y ffmpeg       # Debian / Ubuntu
sudo dnf install -y ffmpeg           # Fedora
winget install Gyan.FFmpeg           # Windows
```

### Kurmadan tek seferlik çalıştırma

ScribeFlow PyPI'da olduğundan, `npx`'in Python karşılıkları doğrudan çalışır:

```bash
uvx scribeflow transcribe ./ders.mp4   # kurmadan tek sefer (uv)
pipx install scribeflow                 # izole global kurulum
```

### İsteğe bağlı eklentiler

Sadece ihtiyacınız olanı kurun:

```bash
pip install 'scribeflow[web]'      # tarayıcı arayüzü:  scribeflow web
pip install 'scribeflow[url]'      # doğrudan URL'den deşifre (yt-dlp)
pip install 'scribeflow[drive]'    # Google Drive kaynağı
```

<details>
<summary>Gelişmiş arka uçlar (çoğu kişiye gerekmez)</summary>

```bash
pip install 'scribeflow[gpu]'      # torch + CUDA notları (sürücünüze uygun wheel'i siz seçersiniz)
pip install 'scribeflow[cpp]'      # whisper.cpp / pywhispercpp — Apple Silicon Metal GPU yolu
pip install 'scribeflow[openai]'   # openai-whisper (PyTorch referans uygulaması)
```

</details>

<details>
<summary>Klondan (geliştirme için)</summary>

```bash
git clone https://github.com/htahaozlu/scribeflow
cd scribeflow
pip install -e '.[dev]'
```

</details>

> **Homebrew tap:** yakında. PyPI zaten yayında — şimdilik yukarıdaki `pip` / `pipx` / `uvx`'i kullanın.

---

## Kullanım

```bash
scribeflow transcribe <kaynak> [seçenekler]
scribeflow models       # modelleri listele + bilgisayarınız için en iyi seçimi göster
scribeflow doctor       # ffmpeg / cihaz / arka uçları kontrol et
scribeflow gen-notebook <kaynak> -o nb.ipynb   # çalışmaya hazır Colab notebook'u üret
scribeflow web          # tarayıcı arayüzü ([web] eklentisi)
scribeflow --version
```

`<kaynak>` yerel bir dosya/klasör, bir `http(s)://` URL ya da `drive:` yolu olabilir — türü
otomatik algılanır.

**Sık kullanacağınız bayraklar:**

| Bayrak | İşlevi |
| ------ | ------ |
| `--format txt,srt,vtt,json` | Ek çıktılar (virgülle). `txt` hep yazılır. |
| `--language` / `-l` | Konuşulan dil: `tr` (varsayılan), herhangi bir kod ya da `auto`. |
| `--out DİZİN` | Transkriptlerin kaydedileceği yer (varsayılan `scribeflow-output/`). |
| `--overwrite` | Önceki çalışmayı yok say, baştan başla. |

<details>
<summary>Gelişmiş bayraklar (çoğu kişi yok sayabilir)</summary>

| Bayrak | İşlevi |
| ------ | ------ |
| `--backend` | `faster-whisper` · `whispercpp` · `openai-whisper` (yoksa otomatik). |
| `--model` | Modeli zorla (varsayılan `large-v3-turbo`). |
| `--device` / `--compute-type` | ör. `cuda` / `float16`, `cpu` / `int8`. |
| `--want speed\|quality\|default` | Otomatik model seçimini yönlendir. |
| `--chunk-minutes` | Devam edilebilir her parçanın uzunluğu (varsayılan 20). |
| `--beam-size` | Çözücü ışın genişliği (varsayılan 5). |
| `--workspace DİZİN` | Ağır ses I/O için geçici dizin (Colab'da Drive dışında tutulur). |
| `--cache-dir DİZİN` | Modellerin indirileceği yer. |
| `--runtime auto\|local\|colab` | Çalışma hedefi. |
| `--source-kind local\|url\|drive\|upload` | Kaynak algılamasını geçersiz kıl. |
| `--config DOSYA` | `scribeflow.toml` yolu. |
| `--json` | Makine-okunur çıktı. |
| `--ui-lang` / `--lang en\|tr` | Arayüz dili (`--language`'dan ayrı). |

</details>

**Örnekler:**

```bash
# Bütün bir klasör, altyazılarla
scribeflow transcribe ./dersler/ --format srt,vtt

# URL'den İngilizce bir konuşma ([url] eklentisi gerekir)
scribeflow transcribe "https://example.com/talk.mp4" -l en

# Colab'da Google Drive'dan bir dosya ([drive] eklentisi gerekir)
scribeflow transcribe "drive:My Drive/roportajlar/oturum1.mp4"
```

---

## Çıktı biçimleri

`.txt` transkript **her zaman** yazılır. Diğerlerini `--format` ile ekleyin:

| `--format` | Aldığınız | Ne için |
| ---------- | --------- | ------- |
| `txt` | Düz transkript | Okuma, arama, not (hep üretilir). |
| `srt` | Zaman kodlu altyazı | Çoğu oynatıcı, YouTube. **Emin değilseniz bunu seçin.** |
| `vtt` | Web altyazısı | Web'de HTML5 `<video>`. |
| `json` | Zamanlı segmentler | Başka araçlara veri. |

Altyazı zaman kodları yalnızca her parça içinde değil, tüm kayıt boyunca doğrudur.

---

## Her yerde çalışır — size uyanı seçin

ScribeFlow donanımınızı algılar ve uygun bir modeli otomatik seçer (`scribeflow models` seçimi
gösterir). **Aşağıdakileri normalde yapılandırmanıza gerek yok** — yalnızca varsayılanları
geçersiz kılmak içindir.

<details>
<summary>Arka uçlar &amp; donanım (gelişmiş)</summary>

Her arka uç aynı çıktı şeklini üretir; aralarında özgürce geçiş yapabilirsiniz.

| Arka uç | En iyi | Kurulum |
| ------- | ------ | ------- |
| `faster-whisper` | CPU ve NVIDIA GPU (varsayılan) | temel kurulum |
| `whispercpp` | Apple Silicon (Metal GPU) | `pip install 'scribeflow[cpp]'` |
| `openai-whisper` | PyTorch referans temeli | `pip install 'scribeflow[openai]'` |

Otomatik seçim kuralları:

- **Apple Silicon** → binary varsa Metal'de whisper.cpp, yoksa CPU'da faster-whisper.
  faster-whisper'ın macOS'ta CUDA/MPS'i yoktur; ScribeFlow bu kombinasyonu önermez.
- **NVIDIA GPU** → `float16` (≥ 8 GB VRAM) ya da `int8_float16`.
- **CPU** → `int8`.
- Genel varsayılan model `large-v3-turbo`'dur; Türkçe için düşük kaliteli / yalnızca-İngilizce
  modeller asla otomatik seçilmez.

Apple Silicon Metal yolunu açmak için ScribeFlow'a whisper.cpp binary + ggml modellerini gösterin:

```bash
export SCRIBEFLOW_WHISPERCPP_BIN=/yol/whisper-cli
export SCRIBEFLOW_WHISPERCPP_MODELS=/yol/ggml-modeller
```

</details>

---

## Kaldığı yerden devam nasıl çalışır

Devam etme bir eklenti değil — motorun çalışma biçimi. Kayıt parçalara bölünür; biten her parça
anında diske yazılır. **Süreci öldürüp aynı komutu yeniden çalıştırın** → ScribeFlow son biten
parçadan sürdürür. Tekrar eden iş yok, bozuk çıktı yok.

Çalışma ortasında model/arka uç değiştirmek reddedilir (çıktılar karışmasın diye) — yeni
ayarlarla baştan başlamak için `--overwrite` verin.

<details>
<summary>Kaputun altında (meraklılar için)</summary>

- **Atomik yazma.** Her parçanın transkripti + `progress.json`, önce geçici dosyaya yazılıp sonra
  yeniden adlandırılır; okuyucu hiçbir zaman yarım dosya görmez, yazma sırasında çökme önceki
  geçerli sürümü bozmaz.
- **RunIdentity koruması.** Özgün arka uç / model / parçalama / seçeneklerle eşleşmeyen bir devam
  girişimi, sonuçları sessizce karıştırmak yerine `CheckpointIdentityError` fırlatır.
- **Belirlenimci çözümleme.** Türkçe varsayılanları (`temperature=0.0`,
  `condition_on_previous_text=False` + tail-prompt ipucu, `vad_filter=True`, `beam_size=5`) bir
  parçanın yeniden çalıştırılınca aynı metni vermesini sağlar; devam etmeyi güvenli kılan budur.

</details>

---

## Google Colab'da ücretsiz GPU

Hızlı bir bilgisayarınız yok mu? Bir notebook üretip ScribeFlow'u tarayıcıda ücretsiz çalıştırın:

```bash
scribeflow gen-notebook ./ders.mp4 -o scribeflow_colab.ipynb
```

[Colab](https://colab.research.google.com/)'da açıp hücreleri sırayla çalıştırın — Drive'ı bağlar,
ScribeFlow'u kurar, deşifre eder ve devam eder. URL ve Drive kaynakları doğru eklentiyi otomatik
ekler.

<details>
<summary>Kopan Drive bağlantısına neden dayanır</summary>

Colab'ın Google Drive bağlaması yazma sırasında kopabilir (`OSError: [Errno 107] Transport endpoint
is not connected`). ScribeFlow ağır, sık değişen I/O'yu (ses parçaları, geçici dosyalar) yerel
`/content` alanında tutar; Drive'a yalnızca küçük, kalıcı transkript + kontrol noktalarını yazar.
Bağlama kesilse bile yazılmış transkriptleriniz güvendedir ve çalışma devam eder.

</details>

---

## Yapılandırma

Ayarlar şu sırayla çözülür: **CLI bayrakları → `scribeflow.toml` → ortam değişkenleri →
varsayılanlar**. Tam başvuru: **[docs/CONFIG.md](docs/CONFIG.md)**.

```toml
# scribeflow.toml — varsayılanlarınızı sabitleyin
[backend]
model = "large-v3-turbo"
[transcribe]
language = "tr"
[output]
formats = ["txt", "srt"]
```

| Ortam değişkeni | Amaç |
| --------------- | ---- |
| `SCRIBEFLOW_LANG` | Varsayılan arayüz dili (`en` / `tr`). |
| `SCRIBEFLOW_WHISPERCPP_BIN` / `..._MODELS` | whisper.cpp binary + ggml modelleri (Apple Silicon). |
| `NO_COLOR` | Renkli çıktıyı kapat (boruya yazınca da otomatik kapanır). |

---

## Sınırlamalar

- **Yalnızca deşifre** — çeviri yok, konuşmacı etiketi (diarization) yok.
- **Segment düzeyinde zaman kodu** (cümle bazında), kelime düzeyinde değil.
- **Yalnızca yerel modeller** — v1'de bulut deşifre API'si yok.
- **Girdiler:** `ffmpeg`'in çözebildiği her şey (yaygın ses/video biçimleri).
- Kalite, alttaki Whisper modeli kadardır; önemli kullanımlarda sonucu gözden geçirin.

---

## Katkı

Katkılar memnuniyetle — bkz. **[CONTRIBUTING.md](CONTRIBUTING.md)**.

```bash
pip install -e '.[dev]'
pytest && ruff check . && mypy
```

## Lisans

[Apache-2.0](LICENSE).
