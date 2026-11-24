# Rejestr pacjentów z chorobą przewlekłą

Prototyp zaliczeniowy na danych syntetycznych. Zakres opisuje [SPEC.md](SPEC.md),
a kolejność prac i kryteria odbioru — [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## Aktualny stan

Ukończono etapy 1–5. Aplikacja obejmuje sesje, role, lokalny Bootstrap, audyt,
modele kliniczne i raportu, wspólną walidację, administrację, `seed_demo`, pełną
ścieżkę HTML pacjent → rozpoznanie → wizyta → pomiar, zapisane raporty i REST API
z opisem OpenAPI.
Administrator może zarządzać pacjentami, rozpoznaniami, wizytami, pomiarami,
słownikiem oraz kontami przez Django Admin. Raporty w administracji można
tworzyć i edytować z przeliczeniem oraz usuwać; każda zmiana ma audyt.
Personel i administrator mogą przeglądać, dodawać, poprawiać i usuwać dane
kliniczne przez **Pacjentów** i tworzyć zestawienia przez **Raporty**.

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
Zależności aplikacji i ich zależności pośrednie są przypięte w `requirements.txt`.

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

### Praca z rejestrem

1. W **Pacjentach** wyszukaj imię lub nazwisko i opcjonalnie wybierz ICD-10.
   Wyszukiwanie obejmuje także kilka członów, np. `Anna Testowa`.
   Wyniki mają po 20 rekordów na stronę, w kolejności nazwisko, imię i id;
   przejście na następną stronę zachowuje filtry.
2. Wybierz **Dodaj pacjenta**, zapisz dane i przejdź do jego karty.
3. Na karcie wybierz **Dodaj rozpoznanie**. Lista pokazuje kod i nazwę ICD-10;
   ten sam kod można przypisać pacjentowi tylko raz.
4. Wybierz **Dodaj wizytę**, podaj datę i opcjonalną notatkę.
   Autor jest ustawiany z zalogowanego konta i nie zmienia się przy edycji.
5. Na stronie wizyty wybierz **Dodaj pomiar**: glukoza we krwi (`mg/dL`)
   albo masa ciała (`kg`). Jednostka obok wartości reaguje na wybór rodzaju.
   Nazwy opcji i opis wartości zawierają jednostki również bez JavaScript.
6. Linki w tabelach prowadzą do szczegółów. Każdy rekord ma edycję i stronę
   potwierdzenia usunięcia; sam GET nie usuwa danych. Najpierw usuwa się
   pomiary, następnie wizyty i rozpoznania, a na końcu pacjenta.
   Próba usunięcia rekordu z zależnościami wyświetla powód blokady.

Pacjent rozpoznania/wizyty oraz wizyta pomiaru wynikają z adresu strony.
Interfejs nie pozwala przenosić tych rekordów między kartami przez formularz.
Notatki są zwykłym, escapowanym tekstem z zachowaniem podziału na wiersze.

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
  i ochroną zależności. Widoki HTML rejestrują odczyty list i szczegółów,
  w tym listy rozpoznań/wizyt na karcie pacjenta, pomiary na stronie wizyty
  oraz wyświetlany słownik ICD-10. Otwarcie formularza edycji lub potwierdzenia
  usunięcia zapisuje odczyt obiektu. CRUD zapisuje jeden wpis zmiany danego
  rekordu w tej samej transakcji co dane; błąd audytu wycofuje zapis/usunięcie.
  Parametry wyszukiwania, notatki i zawartość odpowiedzi nie trafiają do audytu.

## Wspólna walidacja

Reguły znajdują się w `registry/models.py` i `registry/validation.py`.
Formularze ModelForm (także w administracji) wywołują `full_clean()` Django.
Serializery używają `validate_model_instance(instance, attrs)`, przekładają błędy
modelu na standardowe błędy pól DRF i zapisują znormalizowane wartości. Funkcja
sprawdza kopię pełnego obiektu, więc PATCH uwzględnia wszystkie daty i relacje.

Przy zapisie z kodu trzeba jawnie wywołać `full_clean()` albo tę funkcję:
`save()`, `objects.create()`, `update()` i operacje bulk nie uruchamiają walidacji
modelu. W bazie jest dodatkowo ograniczenie unikalności `(patient, icd10)`.
Relacje kliniczne i `Report.icd10` używają `PROTECT`; autorzy mają `SET_NULL`.
Pomiar przechowuje tylko wizytę, rodzaj i Decimal, a jednostka, LOINC i kategoria
FHIR wynikają z `Measurement.DEFINITIONS`.

## Raporty

W **Raportach** wybierz **Dodaj raport**, podaj nazwę, początek i koniec okresu
oraz opcjonalnie wpis słownika ICD-10. **Zapisz i przelicz** zapisuje parametry
i wynik. Okres obejmuje obie daty graniczne. Brak kodu oznacza **Wszystkie
rozpoznania** i obejmuje również pacjentów bez rozpoznań.

Liczba pacjentów to liczba różnych osób z wizytami w wybranym okresie.
Filtr ICD-10 uwzględnia rozpoznanie tylko wtedy, gdy jego data nie jest późniejsza
niż data wizyty. Dodatkowe rozpoznania nie powielają wizyt ani pomiarów.
Glukoza i masa ciała mają osobne liczności, średnie, minima i maksima.
Brak pomiarów oznacza liczność 0 i statystyki `null`, wyświetlane jako
**Brak pomiarów**. Statystyki liczone są z Decimal, zaokrąglane do dwóch miejsc
metodą `ROUND_HALF_UP` i przechowywane w JSON jako ciągi znaków.

Szczegóły pokazują zapisaną migawkę i czas ostatniego obliczenia (`updated_at`).
Zmiana danych klinicznych nie odświeża raportu. Aby odświeżyć wynik, wybierz
**Edytuj i przelicz**, a następnie **Zapisz i przelicz** — nawet bez zmiany
parametrów. Usunięcie raportu wymaga potwierdzenia.

Wspólna funkcja `registry.services.calculate_report` nie zapisuje danych ani
audytu. HTML korzysta z `save_report`, który obejmuje walidację, obliczenie,
zapis i pojedynczy wpis audytu jedną transakcją. Django Admin korzysta z tego
samego kalkulatora w swojej transakcji zapisu i audytu. API korzysta z `save_report`,
tak jak HTML. Autor jest ustawiany przy utworzeniu i zachowywany podczas edycji.
Średnia jest liczona w Pythonie z Decimal.

## REST API

Aktywne konta z grupy `personel` i superużytkownicy mogą korzystać z tych samych
danych przez interfejs HTML i API. Logowanie przez `/accounts/login/` zakłada
sesję Django. Klient API zachowuje ciasteczka `sessionid` i `csrftoken`. Przy
`POST`, `PUT`, `PATCH` i `DELETE` przesyła także aktualną wartość `csrftoken`
w nagłówku `X-CSRFToken`. Po zalogowaniu Django zmienia token. Wylogowanie
wymaga `POST /accounts/logout/` z CSRF.

| Zasób | Adres kolekcji | Filtry listy |
| --- | --- | --- |
| Pacjenci | `/api/v1/patients/` | `search` po imieniu lub nazwisku, `icd10` jako kod, np. `I10` |
| Rozpoznania | `/api/v1/diagnoses/` | `patient` jako ID pacjenta |
| Wizyty | `/api/v1/visits/` | `patient`, `date_from`, `date_to`. Zakres dat `YYYY-MM-DD` obejmuje obie granice. |
| Pomiary | `/api/v1/measurements/` | `visit` jako ID wizyty |
| Raporty | `/api/v1/reports/` | |
| Słownik ICD-10 | `/api/v1/icd10/` | `search` po kodzie lub nazwie |

Pierwsze pięć kolekcji obsługuje `GET` i `POST`. Adres z `/{id}/` obsługuje
`GET`, `PUT`, `PATCH` oraz `DELETE`. Słownik udostępnia `GET` listy i szczegółów.
Listy zwracają po 20 rekordów i pola `count`, `next`, `previous`, `results`.
Pacjenci są sortowani po nazwisku, imieniu i ID, wizyty od najnowszej daty i po
ID rosnąco, a pozostałe listy po ID.

Treść żądań ma format JSON, a pola powiązań przyjmują identyfikatory. Przy
`PUT` podaj wszystkie pola wymagane. `PATCH` zachowuje pominięte parametry.
Raport z `icd10: null` lub pominiętym `icd10` przy `POST` albo `PUT` obejmuje
wszystkie rozpoznania. Każdy zapis raportu przelicza `result`, a `GET` zwraca
zapisaną migawkę. Identyfikator, autor, znaczniki czasu i wynik są polami
do odczytu.

Odpowiedź `201` oznacza utworzenie, `200` oznacza odczyt lub edycję, a `204`
oznacza usunięcie. Błędy walidacji zwracają `400` z listą komunikatów dla
odpowiedniego pola. Brak sesji, roli lub poprawnego tokenu CSRF daje `403`,
brak rekordu lub strony `404`, a blokada usunięcia przez zależności `409`
z wyjaśnieniem w `detail`. API zapisuje audyt odczytów list i szczegółów oraz
jeden wpis dla każdej udanej zmiany w tej samej transakcji co rekord.

### Przykład z PowerShell

Przy uruchomionym serwerze i koncie `demo-personel` zaloguj się, wyszukaj
pacjentów z I10 i utwórz przykładowy rekord.

```powershell
$apiBase = "http://127.0.0.1:8000"
$loginUrl = "$apiBase/accounts/login/"
Invoke-WebRequest $loginUrl -UseBasicParsing -SessionVariable registrySession | Out-Null
$registryCredential = Get-Credential -UserName "demo-personel" -Message "Konto rejestru"
Invoke-WebRequest $loginUrl -UseBasicParsing -WebSession $registrySession -Method Post -Body @{
    username = $registryCredential.UserName
    password = $registryCredential.GetNetworkCredential().Password
    csrfmiddlewaretoken = $registrySession.Cookies.GetCookies([uri]$apiBase)["csrftoken"].Value
} | Out-Null
Remove-Variable registryCredential

Invoke-RestMethod "$apiBase/api/v1/patients/?search=Anna&icd10=I10" -WebSession $registrySession
$csrfToken = $registrySession.Cookies.GetCookies([uri]$apiBase)["csrftoken"].Value
$patientJson = @{
    first_name = "Ada"
    last_name = "Przykładowa"
    birth_date = "1990-01-01"
    gender = "female"
} | ConvertTo-Json
Invoke-RestMethod "$apiBase/api/v1/patients/" -WebSession $registrySession -Method Post `
    -ContentType "application/json; charset=utf-8" -Headers @{ "X-CSRFToken" = $csrfToken } -Body $patientJson
```

### OpenAPI

Uprawnione konta mogą pobrać schemat JSON z `/api/schema/`. Schemat zawiera
parametry, pola żądań i odpowiedzi oraz przykłady pomiaru i raportu. Po zmianie
kontraktu wygeneruj ponownie i zweryfikuj [docs/openapi.yaml](docs/openapi.yaml)
w sesji z ustawionym `SECRET_KEY`.

```powershell
.\.venv\Scripts\python.exe manage.py spectacular --file docs/openapi.yaml --validate --fail-on-warn
```

## Sprawdzenie etapów 1–5

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
Testy HTML obejmują pełny cykl CRUD (oba rodzaje pomiarów), wyszukiwanie,
filtry, stabilne sortowanie, paginację, walidację, wszystkie role i ścieżki,
nieistniejące lub niespójne adresy, blokady usunięcia, escapowanie notatek,
audyt odczytów i zmian oraz atomowość create/update/delete każdego modelu.
Osobny scenariusz z `Client(enforce_csrf_checks=True)` sprawdza brak tokenu
na wszystkich formularzach i pełną ścieżkę z poprawnym tokenem.
Sprawdzenie HTML nie zastępuje pełnego odbioru dostępności przewidzianego w etapie 7.

Testy raportów sprawdzają stałą próbkę A/B/C, daty graniczne i datę rozpoznania,
brak podwójnego zliczania, brak filtra, puste zbiory, obie jednostki, precyzję
i zaokrąglanie, trwałość migawki i przeliczenie przy każdym zapisie. Obejmują
również role, CSRF, błędy formularza, escapowanie nazwy, audyt odczytów/CRUD,
autora i wycofanie zmian po błędzie audytu w HTML oraz administracji.

Testy `APITestCase` obejmują CRUD i PUT/PATCH, role i rzeczywiste sprawdzanie
CSRF sesji, filtry, paginację, pola do odczytu i kody błędów. Sprawdzają też
zgodność raportu z HTML, pojedyncze wpisy audytu, wycofanie zmian po błędzie
audytu oraz zgodność schematu z wersją w repozytorium.

## Źródła techniczne

- [Uwierzytelnianie i sesje Django 5.2](https://docs.djangoproject.com/en/5.2/topics/auth/default/)
- [Django Admin](https://docs.djangoproject.com/en/5.2/ref/contrib/admin/)
- [Uwierzytelnianie sesyjne Django REST Framework](https://www.django-rest-framework.org/api-guide/authentication/#sessionauthentication)
- [Generowanie i walidacja OpenAPI z drf-spectacular](https://drf-spectacular.readthedocs.io/en/stable/customization.html)
- [django-bootstrap5](https://django-bootstrap5.readthedocs.io/en/stable/quickstart.html)
- [Bootstrap 5.3](https://getbootstrap.com/docs/5.3/getting-started/download/)

Lokalne pliki i licencja Bootstrap: `static/vendor/bootstrap/`.
Źródła i warunki słowników: [docs/TERMINOLOGY.md](docs/TERMINOLOGY.md).
