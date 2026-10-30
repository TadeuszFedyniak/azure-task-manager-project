# Task Manager — Azure + Docker Compose + Terraform + Ansible

Edukacyjna aplikacja CRUD w Python/FastAPI, PostgreSQL, Docker Compose i Caddy. Zawiera rejestrację/logowanie, haszowanie haseł Argon2, prywatne zadania użytkownika, CI oraz pliki infrastruktury Azure.

## Wymagania

- Konto Azure z aktywną subskrypcją i uprawnieniami do tworzenia zasobów.
- Git, Docker Desktop (lokalnie), Azure CLI, Terraform, Ansible (wdrożenie VM).
- Domena DNS wskazująca na publiczny IP VM, jeśli chcesz publicznie zaufany certyfikat HTTPS.

## 1. Uruchomienie lokalne

Aplikacja w compose używa Caddy i automatycznego TLS, więc do publicznego uruchomienia potrzebna jest domena. Do lokalnych testów najprościej uruchomić samą aplikację z SQLite:

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Otwórz http://127.0.0.1:8000. Lokalna baza `dev.db` powstanie automatycznie. To tylko tryb developerski — nie używaj go jako produkcyjnego wdrożenia.

## 2. Konfiguracja Azure

Zaloguj się i sprawdź subskrypcję:

```bash
az login
az account show --query id -o tsv
ssh-keygen -t ed25519 -C "azure-task-manager"
```

Skopiuj `terraform/terraform.tfvars.example` do `terraform/terraform.tfvars`. Wstaw ID subskrypcji, ścieżkę do klucza publicznego SSH i swój publiczny adres IP w formacie `x.x.x.x/32`. Nigdy nie ustawiaj reguły SSH na `0.0.0.0/0`.

```bash
cd terraform
terraform init
terraform fmt -check
terraform validate
terraform plan
terraform apply
terraform output -raw public_ip
```

Zapisz publiczny IP VM. Przed uruchomieniem sprawdź plan i szacowane koszty w Azure Portal. Dostępność regionu/rozmiaru VM zależy od subskrypcji i limitów.

## 3. Konfiguracja maszyny przez Ansible

Wróć do katalogu głównego projektu i utwórz `ansible/inventory.ini` na podstawie `ansible/inventory.ini.example`, wpisując IP VM.

```bash
ansible-playbook -i ansible/inventory.ini ansible/playbook.yml
```

Playbook instaluje Docker Engine, plugin Compose i tworzy `/opt/task-manager`.

## 4. Przygotowanie domeny i sekretów

1. W DNS domeny dodaj rekord `A`, np. `tasks.twojadomena.pl`, wskazujący na IP VM.
2. Skopiuj `.env.example` do `.env`.
3. Wygeneruj silne sekrety, np. `openssl rand -hex 32`, i wstaw je w `.env`.
4. Ustaw `DOMAIN` na rzeczywistą domenę oraz `ACME_EMAIL` na swój adres e-mail.
5. Nie commituj `.env`. Caddy musi mieć dostępne porty 80 i 443; certyfikat Let's Encrypt nie zostanie wydany dla samego IP ani domeny, która nie wskazuje na serwer.

## 5. Wdrożenie aplikacji na VM

Umieść repozytorium na GitHub. Na VM sklonuj repozytorium do `/opt/task-manager`, utwórz tam `.env` (z uprawnieniami `chmod 600 .env`) i uruchom:

```bash
cd /opt/task-manager
docker compose up -d --build
docker compose ps
docker compose logs -f
```

Aplikacja będzie dostępna pod `https://twoja-domena`. Port bazy danych nie jest publikowany na hoście.

## 6. CI/CD

Workflow `.github/workflows/ci.yml` uruchamia się po pushu/PR do `main`, sprawdza składnię Pythona i buduje obraz Dockera. To część CI.

Aby uzyskać pełne CD, skonfiguruj w GitHub Actions środowisko `production` i sekrety:
- `VM_HOST`: publiczny IP VM lub domena SSH.
- `VM_USER`: nazwa administratora.
- `VM_SSH_KEY`: prywatny klucz SSH wdrożeniowy (wklej zawartość; klucz powinien być dedykowany do CI).
- `VM_APP_PATH`: `/opt/task-manager`.

Następnie dodaj do workflow krok SSH, który wykona na VM `cd /opt/task-manager && git pull && docker compose up -d --build`. W tym wariancie repozytorium na VM musi być już sklonowane, a konto wdrożeniowe musi mieć ograniczony dostęp. Nie przechowuj klucza prywatnego w repozytorium. Dla mocniejszego rozwiązania użyj GitHub OIDC do Azure dla operacji Azure i osobnego, ograniczonego kanału wdrożenia do VM.

**Uwaga:** obecny workflow to CI, a nie kompletne automatyczne CD. Dodaj krok wdrożeniowy dopiero po skonfigurowaniu sekretów i przetestowaniu SSH, aby uniknąć przypadkowego dostępu do serwera.

## 7. Bezpieczeństwo — co pokazać prowadzącemu

- **HTTPS/TLS:** Caddy automatycznie pobiera i odnawia certyfikat Let's Encrypt dla domeny.
- **Hasła:** w bazie zapisuje się hash Argon2id, nie hasło jawne.
- **Sesja:** podpisane ciasteczko sesyjne; w chmurze `COOKIE_SECURE=true` wymusza flagę Secure.
- **Separacja:** PostgreSQL nie ma opublikowanego portu hosta; jest dostępny tylko w sieci Dockera.
- **Sieć Azure:** otwarte są 80/443 oraz SSH tylko z wskazanego IP.
- **Dane trwałe:** named volume `postgres_data`.
- **Sekrety:** `.env` jest ignorowany przez Git.
- **Dostęp do rekordów:** każde zadanie jest pobierane z warunkiem `owner_id`, więc użytkownik nie powinien modyfikować cudzych zadań.

## 8. Testy do demonstracji

1. Zarejestruj użytkownika z hasłem długości co najmniej 12 znaków.
2. Dodaj dwa zadania, edytuj jedno, oznacz jako zakończone i usuń drugie.
3. Wyloguj się i zaloguj ponownie — zadania powinny pozostać w bazie.
4. Zarejestruj drugiego użytkownika — nie powinien widzieć zadań pierwszego.
5. Otwórz adres HTTPS i sprawdź certyfikat w przeglądarce.
6. Pokaż `docker compose ps`, `docker compose logs`, workflow GitHub Actions oraz zasoby VM w Azure Portal.
7. Pokaż w bazie, że kolumna `password_hash` nie zawiera hasła jawnego.

## 9. Usuwanie zasobów Azure

Po prezentacji usuń zasoby, żeby ograniczyć koszty:

```bash
cd terraform
terraform destroy
```

Sprawdź dokładnie plan przed potwierdzeniem. Usunięcie VM i dysków może oznaczać utratę danych.

## Ograniczenia wersji demonstracyjnej

To projekt zaliczeniowy, a nie gotowy produkt produkcyjny. Przed produkcją dodaj ochronę CSRF, rate limiting dla logowania, migracje Alembic, kopie zapasowe/odtwarzanie, monitoring, skanowanie zależności i obrazów oraz zarządzanie sekretami przez Azure Key Vault. Pliki Terraform i CI/CD należy przetestować w konkretnej subskrypcji przed oddaniem.
