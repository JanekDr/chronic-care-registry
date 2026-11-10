# Rejestr pacjentów z chorobą przewlekłą

Prototyp zaliczeniowy na danych syntetycznych. Zakres opisuje [SPEC.md](SPEC.md),
a kolejność prac i kryteria odbioru — [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## Aktualny stan

Ukończono etapy 1–2: projekt Django, sesje, role, lokalny Bootstrap, audyt,
modele kliniczne i raportu, wspólna walidacja, administracja i `seed_demo`.
Administrator może zarządzać pacjentami, rozpoznaniami, wizytami, pomiarami,
słownikiem oraz kontami przez Django Admin. Raporty w administracji mają na razie
wyłącznie odczyt i usuwanie; ich zapis z przeliczeniem powstanie w etapie 4.
Strony **Pacjenci** i **Raporty** nadal są chronionymi stronami zastępczymi.
Interfejs CRUD personelu, obliczenia raportów, REST API, FHIR i kontener należą
do następnych etapów.

## Uruchomienie lokalne — Windows / PowerShell

Wymagany Python **3.12** z modułem `venv` i programem `pip`. Pierwsza instalacja
zależności wymaga internetu. Bootstrap jest już zapisany w repozytorium.
Wszystkie polecenia wykonuj z katalogu projektu.

### 1. Środowisko i zależności

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Nie trzeba aktywować środowiska ani zmieniać zasad wykonywania skryptów PowerShell.
Zależności etapu 1 oraz ich zależności pośrednie są przypięte w `requirements.txt`.

### 2. Zmienne środowiskowe

```powershell
$env:SECRET_KEY = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(64))"
$env:DEBUG = "1"
$env:ALLOWED_HOSTS = "127.0.0.1,localhost"
```

Wygenerowany klucz pozostaje w środowisku bieżącej sesji PowerShell, bez wypisywania
go na ekran i zapisywania do repozytorium. W nowej sesji ustaw go ponownie.
Zmiana klucza unieważnia dotychczasowe podpisane sesje.

`.env.example` dokumentuje zmienne; aplikacja **nie wczytuje automatycznie `.env`**.
Brak lub pusta wartość `SECRET_KEY` zatrzymuje start z czytelnym błędem.
`DEBUG` domyślnie jest wyłączony; wartość `1` służy lokalnej pracy i serwowaniu
plików statycznych przez `runserver`.

Baza domyślnie znajduje się w `db.sqlite3`. Opcjonalnie można podać inną ścieżkę,
np. do trwałego wolumenu w przyszłym kontenerze:

```powershell
# Katalog docelowy musi istnieć przed migracją.
$env:DATABASE_PATH = Join-Path (Get-Location) "db.sqlite3"
```

### 3. Migracje i dane demonstracyjne

```powershell
.\.venv\Scripts\python.exe manage.py migrate
$env:DEMO_ADMIN_PASSWORD = Read-Host "Hasło nowego konta demo-admin" -MaskInput
$env:DEMO_PERSONEL_PASSWORD = Read-Host "Hasło nowego konta demo-personel" -MaskInput
.\.venv\Scripts\python.exe manage.py seed_demo
Remove-Item Env:DEMO_ADMIN_PASSWORD, Env:DEMO_PERSONEL_PASSWORD
```

`-MaskInput` wymaga PowerShell 7. W Windows PowerShell 5.1 zamiast każdego
`Read-Host ... -MaskInput` użyj poniższego sposobu, zmieniając nazwę zmiennej
na `DEMO_PERSONEL_PASSWORD` przy drugim haśle:

```powershell
$demoCredential = [PSCredential]::new("demo", (Read-Host "Hasło nowego konta" -AsSecureString))
$env:DEMO_ADMIN_PASSWORD = $demoCredential.GetNetworkCredential().Password
Remove-Variable demoCredential
```

Hasła trafiają do środowiska procesu, są sprawdzane przez walidatory Django
i nie są wypisywane przez komendę. Brak lub błędne hasło dla któregokolwiek
nowego konta przerywa inicjalizację bez częściowego zapisu. Hasła nie są wymagane
dla już istniejących kont i nie są resetowane przy ponownym uruchomieniu.
Zamiast danych demo można utworzyć własnego administratora przez
`manage.py createsuperuser`.

`seed_demo` tworzy grupę `personel`, aktywnego superusera `demo-admin`, konto
`demo-personel` bez `is_staff`, kody `I10` i `E11.9`, 10 jawnie fikcyjnych
pacjentów, 10 rozpoznań, 20 wizyt i 40 pomiarów obu rodzajów. Daty rozpoznań
i wizyt przy pierwszym utworzeniu są liczone względem dnia inicjalizacji.
Nie tworzy raportów; stała próbka A/B/C do testów raportu jest osobno
w `registry/tests/report_sample.py`.

Inicjalizuj demonstracyjną bazę przed ręcznym dodawaniem danych. Nowe rekordy
demo mają zarezerwowane identyfikatory: użytkownicy i ICD-10 `10001–10002`,
pacjenci i rozpoznania `10001–10010`, wizyty `10001–10020`, pomiary
`10001–10040` (każdy zakres w osobnej tabeli). Dzięki temu zmiany nazw, dat,
notatek, rodzaju/wartości pomiaru, loginu czy kodu słownikowego nie zmieniają
tożsamości rekordów demo. Nie używaj tych zakresów do własnych importów.
Istniejące konta o loginach demo i kody o tych samych oznaczeniach są również
wykorzystywane bez nadpisywania. Konta już istniejące zachowują role, aktywność
i grupy; komenda nie podnosi ich uprawnień. Ponowne wykonanie zachowuje pola,
hasła, relacje oraz znaczniki czasu i nie dodaje ponownie audytu. Usunięte
rekordy demo mogą zostać odtworzone; komenda nie służy do resetowania bazy.

### 4. Serwer

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Otwórz [logowanie](http://127.0.0.1:8000/accounts/login/).
Po zalogowaniu aplikacja przechodzi na `/patients/`. Administrator ma także
dostęp do [Django Admin](http://127.0.0.1:8000/admin/).
Zatrzymanie serwera: `Ctrl+C`.

Ten wariant służy lokalnej demonstracji HTTP na `127.0.0.1`.
Wariant sieciowy z HTTPS i bezpiecznymi ciasteczkami oraz kontener są częścią
dalszych etapów planu.

### 5. Własne konto personelu

W Django Admin utwórz grupę o dokładnej nazwie `personel`, następnie użytkownika
i przypisz go do tej grupy. Konto ma być aktywne, bez statusu superuser i bez
statusu „W zespole” (`is_staff`). Status `is_staff` nie jest rolą personelu
w tym projekcie; sam nie przyznaje dostępu do rejestru ani administracji.

`seed_demo` zakłada tę grupę i konto demonstracyjne automatycznie. Administracja
blokuje usuwanie kont; konta autorów należy dezaktywować przez pole „Aktywny”.

## Dostęp i audyt

- Użytkownik niezalogowany jest kierowany do logowania. Aktywny użytkownik
  z grupy `personel` lub superuser może otwierać rejestr; konto bez roli otrzymuje `403`.
- Panel administracyjny wymaga aktywnego superusera ze standardowym statusem
  `is_staff`. Sam status `is_staff`, grupa lub nadane uprawnienia nie wystarczają.
- Logowanie korzysta z mechanizmów Django i CSRF. Wylogowanie wymaga POST i CSRF.
- Audyt przechowuje czas, użytkownika, akcję, typ oraz tekstowy identyfikator obiektu.
  Logowanie i wylogowanie, również przez Django Admin, zapisują zdarzenia.
  Nie zapisujemy haseł ani treści formularzy.
- **Rejestr dostępu** w Django Admin jest tylko do odczytu, również dla superusera.
- Funkcja `registry.services.record_audit` uczestniczy w bieżącej transakcji.
  Administracja zapisuje metadane utworzenia, zmiany i usunięcia danych,
  słownika, kont i grup, w tym zmiany hasła oraz przypisania grup użytkownikowi.
  Zapis i audyt są atomowe. `seed_demo` audytuje tylko nowo utworzone rekordy.
  Akcje zbiorcze są wyłączone; dane usuwa się pojedynczo z potwierdzeniem
  i ochroną zależności. Audyt odczytów rejestru powstanie wraz z widokami danych.

## Wspólna walidacja

Reguły znajdują się w `registry/models.py` i `registry/validation.py`.
Formularze ModelForm (także w administracji) wywołują `full_clean()` Django.
Serializery w etapie 5 mają używać `validate_model_instance(instance, attrs)`,
przekładając `ValidationError.message_dict` na standardowe błędy DRF i zapisując
znormalizowane wartości. Funkcja sprawdza kopię pełnego obiektu, więc PATCH
sprawdza nowe pola razem z niezmienionymi datami i relacjami.

Przy zapisie z kodu trzeba jawnie wywołać `full_clean()` albo tę funkcję:
`save()`, `objects.create()`, `update()` i operacje bulk nie uruchamiają walidacji
modelu. W bazie jest dodatkowo ograniczenie unikalności `(patient, icd10)`.
Relacje kliniczne i `Report.icd10` używają `PROTECT`; autorzy mają `SET_NULL`.
Pomiar przechowuje tylko wizytę, rodzaj i Decimal, a jednostka, LOINC i kategoria
FHIR wynikają z `Measurement.DEFINITIONS`.

## Sprawdzenie etapów 1–2

W sesji z ustawionym `SECRET_KEY`:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe -m pip check
```

Testy używają osobnej bazy testowej. Obejmują role, odebranie dostępu,
logowanie/wylogowanie z włączonym sprawdzaniem CSRF, przekierowania,
powiązania etykiet i opisów/błędów formularza, konfigurację środowiskową,
audyt, wycofanie transakcji i zakaz modyfikacji audytu w administracji.
Dodatkowo sprawdzają modele i formularze: daty, zmianę daty urodzenia i pacjenta,
spacje, duplikaty, istnienie FK, długości notatek, precyzję Decimal, NaN/
nieskończoności, ochronę relacji, autora ustawianego przez serwer, audyt zmian
w administracji oraz powtarzalność inicjalizacji z zachowaniem zmian użytkownika.
Sprawdzenie HTML nie zastępuje pełnego odbioru dostępności przewidzianego w etapie 7.

## Źródła techniczne

- [Uwierzytelnianie i sesje Django 5.2](https://docs.djangoproject.com/en/5.2/topics/auth/default/)
- [Django Admin](https://docs.djangoproject.com/en/5.2/ref/contrib/admin/)
- [django-bootstrap5](https://django-bootstrap5.readthedocs.io/en/stable/quickstart.html)
- [Bootstrap 5.3](https://getbootstrap.com/docs/5.3/getting-started/download/)

Lokalne pliki i licencja Bootstrap: `static/vendor/bootstrap/`.
Źródła i warunki słowników: [docs/TERMINOLOGY.md](docs/TERMINOLOGY.md).
