# Słowniki demonstracyjne

Źródła sprawdzone 10 listopada 2026 r. Aplikacja korzysta z dwóch kodów ICD-10
i dwóch stałych powiązań LOINC; nie pobiera klasyfikacji podczas uruchomienia.
Licencja kodu aplikacji nie zastępuje warunków materiałów terminologicznych.

## ICD-10

Źródło: World Health Organization, *International Statistical Classification of
Diseases and Related Health Problems, 10th Revision*, wersja 2019:
[przeglądarka WHO](https://icd.who.int/browse10/2019/en).

| Kod | Znaczenie w demonstracji |
| --- | --- |
| [I10](https://icd.who.int/browse10/2019/en#/I10) | Nadciśnienie samoistne (pierwotne) |
| [E11.9](https://icd.who.int/browse10/2019/en#/E11.9) | Cukrzyca typu 2 bez powikłań |

Polskie etykiety w demonstracji objaśniają znaczenie kodów; nie stanowią importu
pełnego oficjalnego polskiego wydania klasyfikacji ani narzędzia do kodowania.
Nie używamy krajowej modyfikacji ICD-10-CM.

WHO jest właścicielem praw do ICD-10. Oficjalne
[FAQ dotyczące licencjonowania ICD-10](https://cdn.who.int/media/docs/default-source/publishing-policies/copyright/who-faq-licensing-icd-10.pdf)
rozróżnia wykorzystanie komercyjne, wewnętrzne i niekomercyjne/badawcze;
publiczna przeglądarka pozwala odczytywać klasyfikację. Sam dostęp do przeglądarki
nie jest potwierdzeniem uzyskania prawa do rozpowszechniania pełnej bazy.

Aktualna [strona praw autorskich WHO](https://www.who.int/about/policies/publishing/copyright)
opisuje również klasyfikacje na platformie ICD-11 i warunki CC BY-ND 3.0 IGO.
Nie przenosimy automatycznie tych warunków na starszy zasób ICD-10 z 2019 r.
Projekt zawiera jedynie wskazane dwa oznaczenia i ich krótkie objaśnienia
do syntetycznego pokazu edukacyjnego. Nie występowano o odrębną licencję WHO;
rozszerzenie lub dystrybucja oficjalnej klasyfikacji wymaga ustalenia właściwych
praw z WHO lub wydawcą polskiego wydania. Nie deklarujemy aprobaty WHO.

## LOINC i jednostki

Źródło: publiczne wpisy Regenstrief Institute, Inc. i LOINC Committee.
W `Measurement.DEFINITIONS` przechowujemy oznaczenie i oryginalną angielską
nazwę LOINC. Polskie nazwy rodzaju pomiaru są lokalnymi etykietami aplikacji.

| Rodzaj aplikacji | LOINC i oryginalna nazwa | Jednostka UCUM | Kategoria FHIR |
| --- | --- | --- | --- |
| `blood_glucose` | [2339-0 — Glucose [Mass/volume] in Blood](https://loinc.org/2339-0) | `mg/dL` | `laboratory` |
| `body_weight` | [29463-7 — Body weight](https://loinc.org/29463-7) | `kg` | `vital-signs` |

Pierwsze mapowanie oznacza stężenie masowe we krwi, bez zawężenia do surowicy
lub osocza. Nie tworzymy własnych kodów LOINC ani nie modyfikujemy nazw źródłowych.

[Licencja LOINC](https://loinc.org/kb/license), aktualizacja 6 sierpnia 2026 r.,
dopuszcza bezpłatne wykorzystanie komercyjne i niekomercyjne pod warunkami
licencji. Dla fragmentów w oprogramowaniu wymaga m.in. noty o prawach,
zachowania identyfikatorów i odpowiadających im nazw oraz przestrzegania
ograniczeń zmian i praw do treści stron trzecich. Wymagana nota znajduje się
w [LOINC_short_license.txt](LOINC_short_license.txt); należy zachować ją również
w paczce końcowej. Repozytorium nie zawiera pełnej tabeli ani treści ankiet LOINC.

Stałe mapowanie jest przygotowaniem do etapu 6. Eksport FHIR, profil Body Weight
i walidacja HL7 R4 nie są jeszcze zaimplementowane.
