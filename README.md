# Rejestr pacjentów z chorobą przewlekłą

Prototyp zaliczeniowy na danych syntetycznych. Zakres opisuje [SPEC.md](SPEC.md),
a kolejność prac i kryteria odbioru — [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## Aktualny stan

Etap 1: projekt Django, sesje, role, szablony z lokalnym Bootstrapem i audyt
logowania/wylogowania. Strony **Pacjenci** i **Raporty** są chronionymi stronami
zastępczymi; nie zawierają jeszcze modeli klinicznych, CRUD ani obliczeń.
REST API, FHIR, dane demonstracyjne i kontener będą dodane w kolejnych etapach.

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

### 3. Migracje i administrator

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
```

Wybierz login i hasło w interaktywnym formularzu. Projekt nie tworzy kont
z domyślnym hasłem i nie przechowuje haseł inicjalizacyjnych w kodzie.

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

### 5. Konto personelu w etapie 1

W Django Admin utwórz grupę o dokładnej nazwie `personel`, następnie użytkownika
i przypisz go do tej grupy. Konto ma być aktywne, bez statusu superuser i bez
statusu „W zespole” (`is_staff`). Status `is_staff` nie jest rolą personelu
w tym projekcie; sam nie przyznaje dostępu do rejestru ani administracji.

Automatyczna inicjalizacja grupy, kont i danych przez `seed_demo` należy do etapu 2.
Istniejące konta autorów należy dezaktywować zamiast usuwać.

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
  Późniejsze operacje zmieniające dane muszą obejmować zapis i audyt wspólnym
  `transaction.atomic()`. Audyt odczytów danych i CRUD zostanie podłączony wraz z nimi.

## Sprawdzenie etapu 1

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
Sprawdzenie HTML nie zastępuje pełnego odbioru dostępności przewidzianego w etapie 7.

## Źródła techniczne

- [Uwierzytelnianie i sesje Django 5.2](https://docs.djangoproject.com/en/5.2/topics/auth/default/)
- [Django Admin](https://docs.djangoproject.com/en/5.2/ref/contrib/admin/)
- [django-bootstrap5](https://django-bootstrap5.readthedocs.io/en/stable/quickstart.html)
- [Bootstrap 5.3](https://getbootstrap.com/docs/5.3/getting-started/download/)

Lokalne pliki i licencja Bootstrap: `static/vendor/bootstrap/`.
