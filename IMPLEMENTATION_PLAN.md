# Plan implementacji rejestru pacjentów z chorobą przewlekłą

Data przygotowania: 9 listopada 2026 r.

Podstawa: [SPEC.md](SPEC.md). Specyfikacja pozostaje źródłem wymagań; ten dokument określa kolejność prac, zależności, rezultaty i sposób ich odbioru. Zmiana zakresu wymaga najpierw uzgodnienia i aktualizacji specyfikacji.

Stan początkowy: repozytorium zawierało `SPEC.md`, podstawowy `README.md` i `LICENSE`, bez implementacji aplikacji. Stan aktualny: etap 1 ukończony i sprawdzony 9 listopada 2026 r. Etapy 2–8 pozostają otwarte; zadania zaznaczać po wykonaniu i sprawdzeniu rezultatu.

## 1. Zasady realizacji

- Budować prosty prototyp na danych syntetycznych: jedna placówka, jedna aplikacja Django `registry`, jedna baza SQLite.
- Zachować stos ze specyfikacji: Python 3.12, Django 5.2 LTS, DRF 3.16, Django Templates, django-bootstrap5 i lokalny Bootstrap 5.3. Dokładne wersje poprawek ustalić podczas przygotowania środowiska, sprawdzić razem i przypiąć w `requirements.txt`.
- Używać ORM, ModelForm, widoków generycznych i ModelViewSet; bez dodatkowej warstwy repozytoriów i bez wywoływania własnego API z widoków HTML.
- Współdzielić walidację oraz obliczenia raportów między HTML i REST. Zapis zmiany i audytu wykonywać w jednej transakcji.
- Testy reguł i uprawnień dodawać wraz z funkcjami. Końcowy etap służy odbiorowi całego rozwiązania.
- Nie rozszerzać zakresu o funkcje wyłączone w SPEC, m.in. import FHIR, integracje zewnętrzne, wykresy, eksport PDF/Excel z aplikacji, React, JWT i dodatkowe usługi.

## 2. Kolejność i zależności

| Etap | Rezultat | Zależność |
| --- | --- | --- |
| 1 | Uruchamialny projekt, sesje, role i mechanizm audytu | Brak |
| 2 | Modele, migracje, walidacja i dane demonstracyjne | Etap 1 |
| 3 | Pełna ścieżka pacjent → rozpoznanie → wizyta → pomiar w HTML | Etap 2 |
| 4 | Wspólne obliczenia i zapisane raporty w HTML | Etapy 2–3 |
| 5 | REST API oraz opis OpenAPI | Etapy 2–4 |
| 6 | Eksport pacjenta do FHIR R4 | Etapy 2, 3 i 5 |
| 7 | Odbiór funkcji, bezpieczeństwa i dostępności | Etapy 1–6 |
| 8 | Kontener, instrukcje, dokumentacja i komplet materiałów do oddania | Etap 7; dokumentację rozwijać od etapu 1 |

Nie przechodzić do kolejnego etapu z niespełnionym kryterium odbioru jego zależności. Nie przypisywać terminów ani osób bez ustalenia dostępności zespołu; rzeczywisty podział pracy rejestrować na bieżąco.

## 3. Etap 1 — szkielet projektu, logowanie i dostęp

Odniesienie: SPEC §2, §3, §9 i §11.

- [x] Utworzyć środowisko Python 3.12, projekt `config`, aplikację `registry` i `manage.py`.
- [x] Przygotować `requirements.txt`, konfigurację szablonów, plików statycznych, strefy czasowej, języka polskiego i SQLite.
- [x] Ustawić ścieżkę bazy tak, aby później można było skierować ją do trwałego wolumenu kontenera.
- [x] Dodać `.gitignore` dla środowiska wirtualnego, bazy, sekretów i plików generowanych oraz `.env.example` zawierający wyłącznie przykładowe ustawienia bez sekretów.
- [x] Pobierać `SECRET_KEY` ze środowiska. Opisać konfigurację lokalną, w tym sposób przekazania zmiennych środowiskowych; sam plik `.env` nie jest automatycznie odczytywany przez Django.
- [x] Skonfigurować logowanie przez `/accounts/login/`, wylogowanie przez POST i CSRF także dla formularza logowania.
- [x] Przygotować wspólne sprawdzanie roli: grupa `personel` albo superuser. W HTML niezalogowany użytkownik trafia do logowania; zalogowany bez roli nie otrzymuje danych.
- [x] Przygotować wspólny szablon z nawigacją i formularzami django-bootstrap5, w tym formularzem logowania. Administracja widoczna wyłącznie dla administratora.
- [x] Umieścić Bootstrap CSS/JS w lokalnym `static/` i zachować informacje licencyjne.
- [x] Dodać model `AuditLog`, pierwszą migrację, funkcję zapisu audytu oraz obsługę zdarzeń logowania i wylogowania.
- [x] Udostępnić audyt tylko administratorowi w Django Admin, bez możliwości dodawania, zmiany lub usuwania wpisów.
- [x] Dodać testy dostępu dla użytkownika niezalogowanego, bez roli, personelu i administratora.

**Kryterium odbioru:** projekt przechodzi `python manage.py check` i migracje; można się zalogować i wylogować; dostęp wynika z roli; zdarzenia sesji trafiają do audytu; formularz logowania korzysta z lokalnego Bootstrap i django-bootstrap5.

**Wynik odbioru, 9 listopada 2026 r.:** migracje wykonane na pustej bazie; `check`, `makemigrations --check --dry-run` i `pip check` bez błędów; 24 testy zakończone powodzeniem. Uruchomiony lokalny serwer zwrócił formularz logowania, przekierował niezalogowanego użytkownika ze stron pacjentów/raportów i udostępnił lokalne CSS/JS Bootstrap oraz CSS aplikacji. Reguły ról, sesje, CSRF, audyt i powiązania etykiet/opisów/błędów sprawdzono automatycznie. Pełny odbiór dostępności pozostaje w etapie 7. Strony pacjentów i raportów są na razie stronami zastępczymi; konta/grupę można utworzyć ręcznie według README, a `seed_demo` powstanie w etapie 2.

## 4. Etap 2 — model danych, walidacja i inicjalizacja

Odniesienie: SPEC §4, §8 i §10.

- [ ] Dodać modele `Patient`, `ICD10Code`, `Diagnosis`, `Visit`, `Measurement` i `Report` z polami, długościami, znacznikami czasu i typami ze specyfikacji.
- [ ] Ustawić `PROTECT` na relacjach klinicznych i `Report.icd10`; odwołania do autorów mogą mieć `SET_NULL`. Nie powielać pacjenta, daty ani jednostki w modelu pomiaru.
- [ ] Dodać bazowe ograniczenie unikalności `(patient, icd10)` oraz migracje.
- [ ] Zdefiniować dwa rodzaje pomiarów i ich stałe mapowanie jednostek, kodów LOINC oraz kategorii FHIR.
- [ ] Zaimplementować współdzieloną walidację: wymagane imię i nazwisko po przycięciu spacji, daty względem urodzenia i dnia bieżącego, istniejący kod słownikowy, dodatni skończony Decimal oraz poprawny okres raportu.
- [ ] Sprawdzać zmianę daty urodzenia względem już istniejących rozpoznań i wizyt. Walidować również zmianę powiązanego pacjenta w rozpoznaniu lub wizycie.
- [ ] Ustalić jeden sposób wywoływania walidacji z ModelForm i serializerów; nie zakładać, że samo `save()` modelu uruchamia `full_clean()`. Przy PATCH uwzględniać także niezmieniane wartości istniejącego obiektu.
- [ ] Zarejestrować modele w Django Admin. Słownik i konta są zarządzane przez administratora; konta autorów dezaktywować zamiast usuwać.
- [ ] Objąć zmiany danych dostępne przez Django Admin właściwą walidacją i audytem. Zapobiec obchodzeniu reguł przez akcje zbiorcze.
- [ ] Przygotować `seed_demo`: słownik obejmujący co najmniej `I10` i `E11.9`, grupę `personel`, konta i około 10 fikcyjnych pacjentów z zależnościami.
- [ ] Pobierać hasła inicjalizacyjne ze środowiska. Ponowne uruchomienie inicjalizacji nie może duplikować danych, resetować haseł ani nadpisywać zmian użytkownika.
- [ ] Oddzielić stałą próbkę testową raportów od danych demonstracyjnych, aby testy nie zależały od ręcznych zmian bazy.
- [ ] Dodać testy reguł dat, spacji, duplikatów, precyzji/liczby cyfr Decimal, wartości niedodatnich, NaN/nieskończoności i ochrony relacji.

**Kryterium odbioru:** migracje działają na pustej bazie; modele egzekwują wymagane reguły; dwukrotne wykonanie `seed_demo` pozostawia te same rekordy i zachowuje zmiany użytkownika.

## 5. Etap 3 — interfejs rejestru i CRUD

Odniesienie: SPEC §3–5 i §9.

- [ ] Przygotować listę pacjentów: wyszukiwanie po imieniu/nazwisku, filtr ICD-10, stronicowanie po 20 rekordów i stabilny porządek po nazwisku, imieniu oraz id.
- [ ] Przygotować kartę pacjenta z danymi, rozpoznaniami i wizytami oraz formularze dodania i edycji pacjenta.
- [ ] Dodać tworzenie, odczyt, edycję i usuwanie rozpoznań przypisanych do pacjenta.
- [ ] Dodać tworzenie, szczegóły, edycję i usuwanie wizyt; autora ustawia serwer.
- [ ] Dodać tworzenie, odczyt, edycję i usuwanie pomiarów z poziomu wizyty. Wyświetlać jednostkę właściwą dla rodzaju pomiaru.
- [ ] Współdzielić szablony formularzy; stosować etykiety, opisy, błędy i standardowe widgety Django.
- [ ] Wprowadzić potwierdzenie usuwania w HTML. `ProtectedError` przekładać na czytelny komunikat z przyczyną blokady, bez błędu serwera.
- [ ] Zapisywać odczyty list/szczegółów i operacje CRUD w audycie, bez treści notatek i danych odpowiedzi. Zmiana wraz z audytem ma być atomowa.
- [ ] Sprawdzić, że notatki są wyświetlane jako zwykły, escapowany tekst, a niedozwolone żądanie nie zmienia danych.
- [ ] Dodać testy formularzy i widoków dla podstawowej ścieżki, błędów walidacji, uprawnień, CSRF i blokad usunięcia.

**Kryterium odbioru:** personel wykonuje pełną ścieżkę dodania pacjenta, rozpoznania, wizyty i obu rodzajów pomiarów; może je poprawić i usuwać w kolejności zgodnej z zależnościami; odpowiednie zdarzenia są w audycie.

## 6. Etap 4 — raporty i ich zapis

Odniesienie: SPEC §4–6 i §10.

- [ ] Zaimplementować jedną funkcję obliczającą raport w `registry/services.py`, używaną później również przez API.
- [ ] Wybierać wizyty w okresie domkniętym. Opcjonalny filtr ICD-10 uwzględnia wyłącznie rozpoznania z `diagnosed_on <= visit_date`.
- [ ] Zastosować `Exists` lub podzapytanie, aby wiele rozpoznań pacjenta nie powielało wizyt i pomiarów.
- [ ] Obliczać liczbę wizyt i różnych pacjentów oraz oddzielne `count`, `avg`, `min`, `max` dla glukozy i masy ciała.
- [ ] Użyć Decimal, określić jawnie sposób zaokrąglania do dwóch miejsc i zapisywać wartości dziesiętne wyniku jako ciągi znaków. Dla pustych zbiorów zapisywać `0` i `null` zgodnie z SPEC.
- [ ] Dodać listę, formularz, szczegóły i potwierdzenie usunięcia raportu. Parametr ICD-10 jest identyfikatorem wpisu słownika albo brakiem wartości.
- [ ] Na utworzenie i każdy zapis edycji obliczać i zapisywać wynik wraz z audytem w jednej transakcji. Użyć przycisku „Zapisz i przelicz”.
- [ ] Przy odczycie zwracać zapisany wynik bez przeliczenia; `updated_at` wykorzystać jako moment ostatniego obliczenia.
- [ ] Wyświetlać parametry, kod lub „Wszystkie rozpoznania”, definicję liczby pacjentów oraz „Brak pomiarów” tam, gdzie brak statystyk.
- [ ] Dodać test próbki A/B/C: dla I10 w październiku 2026 wynik wynosi 1 pacjent, 2 wizyty, 2 pomiary glukozy, średnia `110.00`, minimum `100.00`, maksimum `120.00`.
- [ ] Sprawdzić dodatkowe rozpoznanie pacjenta A, wizytę przed datą rozpoznania, obie granice okresu, brak filtra, pusty wynik i niezależność zapisanej migawki od późniejszej zmiany pomiaru.

**Kryterium odbioru:** wyniki zgadzają się z próbką SPEC, odczyt zachowuje migawkę, a zapis edycji odświeża ją na aktualnych danych.

## 7. Etap 5 — REST API i OpenAPI

Odniesienie: SPEC §7 i §9–10.

- [ ] Dodać serializery i ModelViewSet dla pacjentów, rozpoznań, wizyt, pomiarów i raportów pod `/api/v1/` oraz słownik ICD-10 wyłącznie do odczytu.
- [ ] Wykorzystać walidację z etapu 2 oraz obliczenia raportów z etapu 4. Pola autora, czasu i wyniku ustawić tylko do odczytu.
- [ ] Ustawić `SessionAuthentication`, sprawdzanie roli na każdym zasobie i CSRF dla zmian. API ma odrzucać brak dostępu kodem `403`, bez przekierowań HTML.
- [ ] Włączyć `PageNumberPagination` z 20 rekordami i stabilne sortowanie: pacjenci po nazwisku, imieniu i id; wizyty po dacie malejąco i id; pozostałe po id.
- [ ] Dodać filtry ze SPEC: wyszukiwanie pacjentów i kod ICD-10, pacjent rozpoznania/wizyty, okres wizyt, wizyta pomiaru oraz wyszukiwanie słownika po kodzie/nazwie.
- [ ] Odrzucać błędny format dat i odwrócony okres w filtrach kodem `400`.
- [ ] Ujednolicić obsługę błędów: standardowe błędy pól DRF, `404` dla brakującego obiektu i `409` przy blokadzie usuwania.
- [ ] Dodać audyt odczytów i zmian; nie dublować zdarzeń, gdy API korzysta ze wspólnych funkcji.
- [ ] Skonfigurować drf-spectacular i chroniony endpoint `/api/schema/`. Opisać pola, sesje/CSRF, uprawnienia, filtry, odpowiedzi i przykłady; eksport FHIR uzupełnić w etapie 6.
- [ ] Wygenerować i sprawdzić plik OpenAPI przeznaczony do dokumentacji. Nie dodawać osobnego interfejsu Swagger.
- [ ] Dodać APITestCase dla CRUD, PUT/PATCH, paginacji, filtrów, pól tylko do odczytu, kodów błędów i zgodności raportu z HTML. Testy CSRF uruchamiać z rzeczywistym sprawdzaniem tokenu.

**Kryterium odbioru:** wszystkie endpointy i odpowiedzi ze SPEC działają; HTML i API egzekwują te same reguły i obliczają ten sam raport; schemat jest dostępny wyłącznie dla uprawnionych użytkowników.

## 8. Etap 6 — eksport HL7 FHIR R4

Odniesienie: SPEC §8 i §10.

- [ ] Zaimplementować mapowanie w `registry/fhir.py` dla R4 4.0.1, bez dodawania UUID do modeli i bez tworzenia serwera FHIR.
- [ ] Tworzyć Bundle `collection` z `timestamp`, jednym Patient oraz jego Condition, Encounter i Observation. Nie eksportować raportów ani kont personelu.
- [ ] Wyliczać identyfikatory przez `uuid5(NAMESPACE_URL, "urn:psim:{ResourceType}:{id}")`, ustawiać `fullUrl` jako `urn:uuid:{uuid}` i kierować wszystkie referencje do wpisów w tej paczce.
- [ ] Zastosować dokładne statusy, systemy kodowania i mapowanie dat ze SPEC. Daty rozpoznania nie traktować jako początku choroby; `Condition.recordedDate` pobierać z `created_at`.
- [ ] Uwzględnić LOINC `2339-0` i `29463-7`, UCUM, kategorie Observation i profil Body Weight.
- [ ] Serializować `valueQuantity.value` jako liczbę JSON i pomijać puste elementy opcjonalne. Sprawdzić zachowanie wartości Decimal w wybranym sposobie serializacji.
- [ ] Dodać `GET /api/v1/patients/{id}/fhir-export/` i przycisk na karcie pacjenta, korzystające z tego samego eksportu.
- [ ] Ustawić `application/fhir+json` i nagłówek pobrania `patient-{id}-fhir.json`; kontrolować rolę i rejestrować eksport w audycie.
- [ ] Uzupełnić OpenAPI o format i przykład odpowiedzi eksportu.
- [ ] Dodać testy typów, kodów, statusów, deterministycznych identyfikatorów, zamknięcia referencji i izolacji danych wskazanego pacjenta, również dla pacjenta bez danych zależnych.
- [ ] Zwalidować przykładowy Bundle oficjalnym walidatorem HL7 dla `4.0.1`; zapisać wersję narzędzia, polecenie i rezultat. Usunąć błędy, a ostrzeżenia przeanalizować i opisać.
- [ ] Udokumentować źródła i warunki wykorzystania podzbioru ICD-10 oraz mapowania LOINC.

**Kryterium odbioru:** pobrany plik zawiera tylko dane wskazanego pacjenta, ma poprawne referencje i liczby JSON oraz przechodzi walidację R4 bez błędów. Walidator pozostaje narzędziem odbioru, a nie zależnością uruchomieniową aplikacji.

## 9. Etap 7 — odbiór całości

Odniesienie: SPEC §5 i §9–10.

- [ ] Uruchomić cały zestaw Django TestCase i DRF APITestCase oraz `python manage.py check`; sprawdzić brak niezapisanych zmian modeli przez `makemigrations --check --dry-run`.
- [ ] Przejść ręcznie CRUD, raport i eksport na koncie personelu oraz zarządzanie słownikiem, kontami i odczyt audytu na koncie administratora.
- [ ] Sprawdzić dostęp bez sesji i bez roli do wszystkich widoków danych, API, schematu oraz eksportu, a także odrzucenie personelu w administracji.
- [ ] Sprawdzić spójność audytu: odczyty list/szczegółów, CRUD, sesje i eksport; brak haseł, notatek i pełnych odpowiedzi; brak zapisanej zmiany po wycofaniu transakcji.
- [ ] Zweryfikować ochronę CSRF i escapowanie notatek oraz brak sekretów i rzeczywistych danych w repozytorium.
- [ ] Sprawdzić formularz logowania i formularze danych: etykiety, `aria-describedby`, `aria-invalid`, widoczne błędy, fokus oraz obsługa wyłącznie klawiaturą.
- [ ] Sprawdzić kontrast i brak przekazywania informacji wyłącznie kolorem; odnieść wyniki do wymagań WCAG 2.2 AA wskazanych w kryteriach kursu. Zapisać faktycznie wykonane sprawdzenia i ograniczenia oceny.
- [ ] Potwierdzić w przeglądarce, że aplikacja po przygotowaniu działa bez CDN i innych zewnętrznych zasobów interfejsu.
- [ ] Zapisać wyniki odbioru i naprawić znalezione błędy; powtarzać testy dotyczące zmienionych obszarów.

**Kryterium odbioru:** scenariusze z tabeli testów SPEC §10 są zaliczone, brak otwartych błędów blokujących i nieuzasadnionych deklaracji zgodności. Bez testów obciążeniowych, rozbudowanej automatyzacji przeglądarki ani celu procentowego pokrycia.

## 10. Etap 8 — uruchomienie i materiały do oddania

Odniesienie: SPEC §11–12. Materiały projektowe rozwijać podczas wcześniejszych etapów, a tutaj sprawdzić ich kompletność i zgodność z implementacją.

### Aplikacja i instrukcja

- [ ] Uzupełnić README o dokładne polecenia dla docelowego systemu: środowisko, instalacja zależności, zmienne środowiskowe, migracje, `seed_demo`, start na `127.0.0.1:8000`, testy i generowanie OpenAPI.
- [ ] Przygotować jeden `Dockerfile` i `docker-compose.yml`: jedna usługa Django, Gunicorn, WhiteNoise, lokalne pliki statyczne z `collectstatic` i SQLite w trwałym wolumenie.
- [ ] Związać port hosta z `127.0.0.1`; opisać migracje i jednorazową inicjalizację kont/danych bez automatycznego resetowania bazy przy starcie.
- [ ] Opisać przekazanie haseł demonstracyjnych bez umieszczania ich w kodzie i repozytorium. Do paczki zaliczeniowej dołączyć dane kont testowych zgodnie z warunkami kursu.
- [ ] Sprawdzić uruchomienie z README w czystym środowisku oraz uruchomienie kontenera, serwowanie statycznych plików i zachowanie danych po odtworzeniu kontenera.
- [ ] Opisać wariant sieciowy z HTTPS przez serwer pośredniczący i bezpiecznymi ciasteczkami; oddzielić go od lokalnej demonstracji HTTP. Nie budować publicznego hostingu.

### Dokumentacja i prezentacja

- [ ] E1: dołączyć formularz tematu i potwierdzenie akceptacji prowadzącego, gdy zostaną udostępnione.
- [ ] E2: przygotować cel, odbiorców, krótki przegląd rozwiązań ze źródłami, wykonalność, ryzyka i potencjał komercjalizacji.
- [ ] E3: przygotować aktualny ERD, opis elementów EDM, słowników ICD-10/LOINC i mapowania FHIR.
- [ ] E4: przygotować diagram komponentów i wdrożenia, plik OpenAPI, przykłady API, opis ról, szyfrowania i audytu.
- [ ] E5: przygotować persony, ścieżki, nawigację i co najmniej pięć makiet: lista pacjentów, karta pacjenta, wizyta z pomiarami, formularz raportu i wynik raportu; dołączyć wyniki sprawdzeń dostępności.
- [ ] E6: opracować kategorie danych, podstawy prawne, ochronę, retencję/usuwanie i uzasadnioną analizę kwalifikacji MDR. Przy opracowywaniu zweryfikować aktualność przepisów wskazanych w SPEC; rozróżnić prototyp syntetyczny i hipotetyczne wdrożenie z danymi rzeczywistymi.
- [ ] E7: przygotować spójną wersję edytowalną i PDF, bibliografię i rzeczywisty podział pracy; porównać układ z właściwym wzorcem kursowym po jego otrzymaniu.
- [ ] E8: zebrać kod, zależności, testy i ich wyniki, dane syntetyczne, przykładowy eksport FHIR wraz z wynikiem walidacji oraz instrukcję uruchomienia.
- [ ] E9: przygotować prezentację i przećwiczyć pokaz trwający 10–12 minut: logowanie → pacjent → rozpoznanie → wizyta → pomiar → raport → eksport FHIR.
- [ ] Zebrać wymagane oświadczenia, w tym rzeczywisty zakres wykorzystania AI.

### Paczka końcowa

- [ ] Przygotować strukturę przekazania: `00_README.txt`, `01_Dokumentacja/`, `02_Aplikacja_kod/`, `03_Aplikacja_uruchom/`, `04_Dane_testowe/`, `05_Prezentacja/`, `06_Oswiadczenia/`.
- [ ] Sprawdzić, że wszystkie materiały odpowiadają tej samej wersji aplikacji, a paczka nie zawiera sekretów środowiska ani danych rzeczywistych.
- [ ] Zweryfikować warunki oddania na e-portalu i opisanym nośniku na podstawie oryginalnych materiałów kursu; przekazanie wykonać zgodnie z ustaleniami zespołu.

**Kryterium odbioru:** inna osoba uruchamia aplikację według instrukcji bez dodatkowych wyjaśnień, przechodzi scenariusz demonstracyjny, a paczka zawiera komplet wymaganych materiałów.

## 11. Materiały zewnętrzne i punkty wymagające weryfikacji

| Materiał lub decyzja | Kiedy potrzebne | Działanie |
| --- | --- | --- |
| Dokładne wersje poprawek zależności | Etap 1 | Sprawdzić zgodność instalacji i przypiąć działający zestaw; nie zmieniać samodzielnie stosu ze SPEC. |
| Źródła i warunki wykorzystania kodów ICD-10/LOINC | Etapy 2 i 6 | Zweryfikować źródła dla użytego podzbioru i udokumentować je. |
| Walidator HL7 i pakiet R4 4.0.1 | Etap 6 | Przygotować narzędzie do walidacji pliku, zachować wynik sprawdzenia. |
| Pełne warunki kursu, formularz tematu i właściwy wzorzec dokumentacji | Dokumentacja i odbiór etapu 8 | Uzyskać oryginalne materiały; SPEC zawiera ich podsumowanie, a nie pełną treść wzorca. Nie blokuje to rozpoczęcia implementacji. |
| Aktualne przepisy i analiza MDR | Opracowanie E6 | Zweryfikować źródła przy pisaniu dokumentacji; nie traktować planu jako analizy prawnej. |
| Skład zespołu, podział pracy, terminy i sposób przekazania | Organizacja oddania | Uzupełniać na podstawie rzeczywistych ustaleń, bez dopisywania fikcyjnych autorów lub wykonanych czynności. |

## 12. Definicja ukończenia projektu

- [ ] Wszystkie etapy mają spełnione kryteria odbioru i zaznaczone wykonane zadania.
- [ ] Funkcje, role, reguły danych, raporty, API i FHIR odpowiadają SPEC.
- [ ] Testy przechodzą, scenariusz ręczny jest sprawdzony, a walidacja przykładowego Bundle jest udokumentowana.
- [ ] Start lokalny i kontenerowy są odtworzone według README na czystym środowisku.
- [ ] Dokumentacja i paczka zaliczeniowa są kompletne oraz zgodne z faktycznym stanem projektu.
