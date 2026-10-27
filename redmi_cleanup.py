#!/usr/bin/env python3
"""
Redmi Cleanup — очистка Xiaomi / Redmi (MIUI) от рекламы, трекеров и
предустановленного мусора через ADB. Root не нужен.

Приложения удаляются только для текущего пользователя
(pm uninstall -k --user 0), сами APK остаются в системном разделе,
поэтому любое удалённое приложение можно вернуть пунктом «Восстановить»
или командой:  adb shell cmd package install-existing <имя.пакета>

Запуск:
    python redmi_cleanup.py           — интерактивное меню
    python redmi_cleanup.py --auto    — рекомендуемая очистка + ускорение
"""

import argparse
import os
import platform
import shutil
import stat
import subprocess
import sys
import time
import urllib.request
import zipfile
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_ADB_DIR = os.path.join(SCRIPT_DIR, "platform-tools")
REMOVED_LOG = os.path.join(SCRIPT_DIR, "removed_packages.txt")

PLATFORM_TOOLS_URL = "https://dl.google.com/android/repository/platform-tools-latest-{os}.zip"

AD_BLOCK_DNS = "dns.adguard-dns.com"

# ---------------------------------------------------------------------------
# Списки пакетов. Формат: (пакет, описание[, пакет-условие])
# Пакет-условие: удалять только если на телефоне есть эта замена
# (например, Mi Browser удаляется, только если установлен Chrome).
# Пакеты, которых нет на телефоне, просто пропускаются.
# ---------------------------------------------------------------------------

# Безопасно для всех: реклама, трекеры, аналитика, китайские сервисы, партнёрский мусор.
RECOMMENDED = [
    # --- Реклама и аналитика MIUI ---
    ("com.miui.msa.global", "MSA — главный источник рекламы в MIUI"),
    ("com.miui.systemAdSolution", "Рекламный модуль MIUI (китайская прошивка)"),
    ("com.xiaomi.ab", "MAB — рекламный сервис Xiaomi"),
    ("com.miui.analytics", "Аналитика / телеметрия Xiaomi"),
    ("com.miui.daemon", "MIUI Daemon — сбор статистики об использовании"),
    ("com.miui.bugreport", "Отправка отчётов об ошибках"),
    ("com.xiaomi.joyose", "Joyose — облачные профили и телеметрия"),
    ("com.miui.contentcatcher", "Сбор данных о контенте приложений"),
    ("com.miui.catcherpatch", "Патч для contentcatcher"),
    ("com.xiaomi.discover", "Обновление системных приложений (навязывает обновления с рекламой)"),
    ("com.xiaomi.gamecenter.sdk.service", "SDK игрового центра Xiaomi"),
    # --- Рекламные приложения и ленты ---
    ("com.mi.globalminusscreen", "App Vault — лента слева от рабочего стола"),
    ("com.miui.personalassistant", "Лента виджетов (китайская прошивка)"),
    ("com.miui.android.fashiongallery", "Карусель обоев — реклама на экране блокировки"),
    ("com.mfashiongallery.emag", "Карусель обоев (другая версия)"),
    ("com.xiaomi.mipicks", "GetApps — магазин приложений Xiaomi с рекламой"),
    ("com.xiaomi.glgm", "Xiaomi Games"),
    ("com.mi.global.bbs", "Mi Community"),
    ("com.mi.global.shop", "Mi Store"),
    ("com.miui.miservice", "Службы и обратная связь"),
    ("com.miui.hybrid", "Быстрые приложения (Quick Apps)"),
    ("com.miui.hybrid.accessory", "Быстрые приложения — дополнение"),
    ("com.miui.yellowpage", "Жёлтые страницы"),
    ("com.miui.huanji", "Mi Mover — перенос данных со старого телефона"),
    ("com.miui.player", "Mi Music (с рекламой)"),
    ("com.miui.videoplayer", "Mi Video (с рекламой)"),
    ("com.mi.globalbrowser", "Mi Browser (с рекламой)", "com.android.chrome"),
    ("com.android.browser", "Mi Browser (с рекламой)", "com.android.chrome"),
    ("com.facemoji.lite.xiaomi", "Клавиатура Facemoji", "com.google.android.inputmethod.latin"),
    # --- Китайские сервисы (за пределами Китая бесполезны) ---
    ("com.miui.voiceassist", "Голосовой ассистент Xiao AI"),
    ("com.miui.voicetrigger", "Активация Xiao AI голосом"),
    ("com.miui.nextpay", "Китайские платежи"),
    ("com.miui.vsimcore", "Виртуальные SIM (Китай)"),
    ("com.miui.virtualsim", "Виртуальные SIM (Китай)"),
    ("com.miui.translation.kingsoft", "Китайский переводчик"),
    ("com.miui.translation.youdao", "Китайский переводчик"),
    ("com.miui.translation.xiaomi", "Китайский переводчик"),
    ("com.miui.translationservice", "Сервис китайских переводчиков"),
    # --- Партнёрские предустановки ---
    ("com.facebook.appmanager", "Facebook App Manager (фоновая служба)"),
    ("com.facebook.services", "Facebook Services (фоновая служба)"),
    ("com.facebook.system", "Facebook App Installer"),
    ("com.facebook.katana", "Facebook"),
    ("com.facebook.orca", "Messenger"),
    ("com.netflix.partner.activation", "Netflix — партнёрская активация"),
    ("com.netflix.mediaclient", "Netflix"),
    ("com.amazon.appmanager", "Amazon App Manager"),
    ("com.amazon.mShop.android.shopping", "Amazon Shopping"),
    ("in.amazon.mShop.android.shopping", "Amazon India"),
    ("com.booking", "Booking.com"),
    ("com.agoda.mobile.consumer", "Agoda"),
    ("com.ebay.mobile", "eBay"),
    ("com.ebay.carrier", "eBay (партнёрский)"),
    ("com.linkedin.android", "LinkedIn"),
    ("com.spotify.music", "Spotify"),
    ("com.zhiliaoapp.musically", "TikTok"),
    ("com.ss.android.ugc.trill", "TikTok"),
    ("com.opera.preinstall", "Opera — партнёрская предустановка"),
    ("com.ironsource.appcloud.oobe", "ironSource — установщик рекламных приложений"),
    ("com.aura.oobe.deutsche", "Aura — установщик рекламных приложений"),
    # --- Лишние сервисы Google (Play Market, сервисы и Chrome НЕ трогаются) ---
    ("com.google.android.feedback", "Отправка отзывов в Google"),
    ("com.google.android.apps.tachyon", "Google Duo / Meet"),
    ("com.google.android.videos", "Google Play Фильмы"),
    ("com.google.android.music", "Google Play Музыка (закрыт)"),
    ("com.google.android.apps.youtube.music", "YouTube Music"),
    ("com.google.android.apps.podcasts", "Google Подкасты"),
    ("com.google.android.apps.subscriptions.red", "Google One"),
    ("com.google.android.apps.magazines", "Google Новости"),
    # --- Мелочи AOSP ---
    ("com.android.egg", "Пасхалка Android"),
    ("com.android.dreams.basic", "Заставка экрана"),
    ("com.android.dreams.phototable", "Заставка экрана «Фото»"),
    ("com.android.bookmarkprovider", "Пустой провайдер закладок"),
]

# Рабочие, но многим не нужные приложения. Удаляйте, только если не пользуетесь.
OPTIONAL = [
    ("com.miui.cleanmaster", "Очистка MIUI (с рекламой)"),
    ("com.miui.cloudservice", "Mi Cloud (без него не работает «Найти устройство»)"),
    ("com.miui.cloudbackup", "Резервное копирование в Mi Cloud"),
    ("com.miui.micloudsync", "Синхронизация Mi Cloud"),
    ("com.xiaomi.payment", "Mi Pay / Mi Credits"),
    ("com.mipay.wallet.in", "Mi Pay (Индия)"),
    ("com.xiaomi.midrop", "ShareMe (Mi Drop)"),
    ("com.miui.mishare.connectivity", "Mi Share"),
    ("com.miui.fm", "FM-радио"),
    ("com.miui.fmservice", "FM-радио — сервис"),
    ("com.miui.compass", "Компас"),
    ("com.miui.weather2", "Погода MIUI (и её виджет)"),
    ("com.miui.notes", "Заметки MIUI"),
    ("com.miui.screenrecorder", "Запись экрана"),
    ("com.xiaomi.scanner", "Сканер QR-кодов"),
    ("com.miui.touchassistant", "Quick Ball (плавающая кнопка)"),
    ("com.miui.phrase", "Часто используемые фразы"),
    ("com.miui.backup", "Локальное резервное копирование MIUI"),
    ("com.xiaomi.migameservice", "Game Turbo"),
    ("com.mi.health", "Mi Health"),
    ("com.xiaomi.xmsf", "Xiaomi Service Framework (пуши Xiaomi; могут перестать работать темы)"),
    ("com.miui.guardprovider", "Проверка приложений на вирусы при установке"),
    ("com.google.android.googlequicksearchbox", "Приложение Google / Ассистент"),
    ("com.google.android.apps.googleassistant", "Google Ассистент"),
    ("com.android.hotwordenrollment.okgoogle", "Распознавание «Окей, Google»"),
    ("com.android.hotwordenrollment.xgoogle", "Распознавание «Окей, Google»"),
    ("com.google.ar.lens", "Google Объектив"),
    ("com.google.android.apps.wellbeing", "Цифровое благополучие"),
    ("com.google.android.youtube", "YouTube"),
    ("com.google.android.gm", "Gmail"),
    ("com.google.android.apps.maps", "Google Карты"),
    ("com.google.android.apps.docs", "Google Диск"),
    ("com.google.android.apps.photos", "Google Фото"),
    ("com.google.android.marvin.talkback", "TalkBack (для слабовидящих)"),
]

# Никогда не удаляются — даже если кто-то добавит их в списки выше.
# Удаление любого из них может привести к бутлупу или сломать телефон.
PROTECTED = {
    "android",
    "com.android.systemui",
    "com.android.settings",
    "com.android.phone",
    "com.android.providers.settings",
    "com.android.vending",
    "com.android.chrome",
    "com.google.android.gms",
    "com.google.android.gsf",
    "com.google.android.webview",
    "com.google.android.inputmethod.latin",
    "com.miui.home",
    "com.miui.securitycenter",
    "com.miui.securitycore",
    "com.lbe.security.miui",
    "com.miui.powerkeeper",
    "com.miui.miwallpaper",
    "com.miui.global.packageinstaller",
    "com.android.thememanager",
    "com.xiaomi.finddevice",
    "com.miui.system",
    "com.miui.rom",
    "com.miui.core",
}


# ---------------------------------------------------------------------------
# Вывод
# ---------------------------------------------------------------------------

def _enable_colors():
    if os.name == "nt":
        os.system("")  # включает ANSI-последовательности в консоли Windows 10+
    return sys.stdout.isatty()


COLORS = _enable_colors()


def color(text, code):
    return f"\033[{code}m{text}\033[0m" if COLORS else text


def ok(msg):
    print(color("  [OK] ", "32") + msg)


def warn(msg):
    print(color("  [!]  ", "33") + msg)


def err(msg):
    print(color("  [X]  ", "31") + msg)


def title(msg):
    print()
    print(color("=" * 64, "36"))
    print(color("  " + msg, "36;1"))
    print(color("=" * 64, "36"))


def ask_yes(question, default=False, assume_yes=False):
    if assume_yes:
        return True
    hint = "[Д/н]" if default else "[д/Н]"
    answer = input(f"  {question} {hint}: ").strip().lower()
    if not answer:
        return default
    return answer in ("д", "да", "y", "yes", "l")  # «l» — «д» в английской раскладке


# ---------------------------------------------------------------------------
# ADB
# ---------------------------------------------------------------------------

class Adb:
    def __init__(self, path):
        self.path = path
        self.serial = None

    def run(self, *args, timeout=120):
        cmd = [self.path]
        if self.serial:
            cmd += ["-s", self.serial]
        cmd += list(args)
        try:
            res = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return 1, "timeout"
        return res.returncode, (res.stdout + res.stderr).strip()

    def shell(self, command, timeout=120):
        return self.run("shell", command, timeout=timeout)

    def prop(self, name):
        return self.shell(f"getprop {name}")[1].strip()

    def packages(self, all_users=False):
        flag = " -u" if all_users else ""
        code, out = self.shell(f"pm list packages{flag}")
        if code != 0:
            return set()
        return {line[len("package:"):].strip() for line in out.splitlines()
                if line.startswith("package:")}


def find_adb():
    exe = "adb.exe" if os.name == "nt" else "adb"
    local = os.path.join(LOCAL_ADB_DIR, exe)
    if os.path.isfile(local):
        return local
    found = shutil.which("adb")
    if found:
        return found
    return None


def download_adb():
    system = platform.system().lower()
    os_name = {"windows": "windows", "darwin": "darwin", "linux": "linux"}.get(system)
    if not os_name:
        err(f"Неизвестная ОС: {system}. Установите ADB вручную.")
        return None
    url = PLATFORM_TOOLS_URL.format(os=os_name)
    archive = os.path.join(SCRIPT_DIR, "platform-tools.zip")
    print(f"  Скачиваю ADB от Google: {url}")
    try:
        urllib.request.urlretrieve(url, archive)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(SCRIPT_DIR)
    except Exception as e:  # noqa: BLE001 — показываем пользователю любую причину
        err(f"Не удалось скачать ADB: {e}")
        return None
    finally:
        if os.path.exists(archive):
            os.remove(archive)
    adb = find_adb()
    if adb and os.name != "nt":
        os.chmod(adb, os.stat(adb).st_mode | stat.S_IEXEC)
    if adb:
        ok("ADB скачан в папку platform-tools")
    return adb


def connect_wifi(adb):
    title("Подключение по Wi-Fi")
    print("  Телефон и компьютер должны быть подключены к одной сети Wi-Fi.")
    print("  1. На телефоне: Настройки → Расширенные настройки → Для разработчиков →")
    print("     включите «Беспроводная отладка» и нажмите на сам пункт.")
    print("  2. Нажмите «Подключение устройства с помощью кода подключения».")
    print("     Появятся код из 6 цифр и адрес вида 192.168.1.5:37000.")
    print("     Не закрывайте это окно на телефоне.")
    print("  (Если телефон уже подключался к этому компьютеру, шаг 2 можно пропустить —")
    print("   просто нажмите Enter.)")

    pair_addr = input("\n  Адрес из окна с кодом (IP:порт): ").strip()
    if pair_addr:
        code = input("  Код из 6 цифр: ").strip()
        _, out = adb.run("pair", pair_addr, code, timeout=30)
        if "Successfully paired" not in out:
            err(f"Не удалось сопрячь: {out or 'нет ответа'}")
            print("       Проверьте адрес и код (код меняется каждый раз при открытии окна).")
            return False
        ok("Телефон сопряжён с компьютером")

    print("\n  3. Закройте окно с кодом. На экране «Беспроводная отладка» указан")
    print("     «IP-адрес и порт» — он отличается от адреса для кода.")
    addr = input("  IP-адрес и порт: ").strip()
    if not addr:
        return False
    _, out = adb.run("connect", addr, timeout=30)
    if "connected to" in out and "failed" not in out:
        ok(f"Подключено по Wi-Fi: {addr}")
        return True
    err(f"Не удалось подключиться: {out or 'нет ответа'}")
    return False


def connect_device(adb, wifi=False):
    title("Подключение телефона")
    adb.run("start-server", timeout=30)
    if wifi:
        connect_wifi(adb)
    printed_help = False
    while True:
        _, out = adb.run("devices")
        devices = []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2:
                devices.append((parts[0], parts[1]))

        ready = [s for s, state in devices if state == "device"]
        unauthorized = [s for s, state in devices if state == "unauthorized"]

        if len(ready) == 1:
            adb.serial = ready[0]
            return True
        if len(ready) > 1:
            print("  Подключено несколько устройств:")
            for i, s in enumerate(ready, 1):
                print(f"    {i}. {s}")
            choice = input("  Номер нужного устройства: ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(ready):
                adb.serial = ready[int(choice) - 1]
                return True
            continue

        if unauthorized:
            warn("Телефон найден, но не разрешил отладку.")
            print("       Разблокируйте экран и нажмите «Разрешить» в окне")
            print("       «Разрешить отладку по USB?» (отметьте «Всегда разрешать»).")
        elif not printed_help:
            warn("Телефон не найден. Проверьте:")
            print("       1. Настройки → О телефоне → 7 раз нажмите на «Версия MIUI»")
            print("       2. Настройки → Расширенные настройки → Для разработчиков:")
            print("          включите «Отладка по USB» и «Установка через USB»")
            print("       3. Подключите кабель (именно для передачи данных, не только зарядки)")
            print("       4. На телефоне в уведомлении USB выберите «Передача файлов»")
            print("       5. Windows: если не видит — поставьте драйвер Google USB Driver")
            print("       Без кабеля: нажмите w, чтобы подключиться по Wi-Fi.")
            printed_help = True

        answer = input("\n  Enter — проверить снова, w — подключиться по Wi-Fi, q — выход: ").strip().lower()
        if answer in ("q", "й"):
            return False
        if answer in ("w", "ц"):
            connect_wifi(adb)


def show_device_info(adb):
    brand = adb.prop("ro.product.brand")
    model = adb.prop("ro.product.model")
    android = adb.prop("ro.build.version.release")
    miui = adb.prop("ro.miui.ui.version.name")
    ok(f"Подключено: {brand} {model}, Android {android}" + (f", MIUI {miui}" if miui else ""))
    if brand.lower() not in ("xiaomi", "redmi", "poco"):
        warn("Это не Xiaomi / Redmi / POCO. Списки рассчитаны на MIUI —")
        warn("лишнее просто не найдётся, но проверьте список перед удалением.")


# ---------------------------------------------------------------------------
# Действия
# ---------------------------------------------------------------------------

def log_removed(serial, packages):
    if not packages:
        return
    with open(REMOVED_LOG, "a", encoding="utf-8") as f:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        for pkg in packages:
            f.write(f"{stamp}\t{serial}\t{pkg}\n")


def read_removed(serial):
    if not os.path.exists(REMOVED_LOG):
        return []
    result = []
    with open(REMOVED_LOG, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) == 3 and parts[1] == serial and parts[2] not in result:
                result.append(parts[2])
    return result


def plan_removal(installed, entries):
    plan = []
    for entry in entries:
        pkg, desc = entry[0], entry[1]
        requires = entry[2] if len(entry) > 2 else None
        if pkg in PROTECTED or pkg not in installed:
            continue
        if requires and requires not in installed:
            continue
        plan.append((pkg, desc))
    return plan


def remove_packages(adb, entries, label, assume_yes=False, pick=False):
    title(label)
    installed = adb.packages()
    if not installed:
        err("Не удалось получить список приложений с телефона.")
        return
    plan = plan_removal(installed, entries)
    if not plan:
        ok("Ничего лишнего из этого списка на телефоне не найдено.")
        return

    for i, (pkg, desc) in enumerate(plan, 1):
        print(f"  {i:>3}. {desc}")
        print(color(f"       {pkg}", "90"))

    if pick:
        print("\n  Введите номера через пробел (например: 1 4 7), «все» — удалить всё,")
        print("  пустая строка — отмена.")
        raw = input("  > ").strip().lower()
        if not raw:
            return
        if raw not in ("все", "all", "dct"):
            nums = {int(x) for x in raw.replace(",", " ").split() if x.isdigit()}
            plan = [p for i, p in enumerate(plan, 1) if i in nums]
            if not plan:
                return
    elif not ask_yes(f"Удалить {len(plan)} приложений?", default=True, assume_yes=assume_yes):
        return

    removed, failed = [], []
    for pkg, desc in plan:
        code, out = adb.shell(f"pm uninstall -k --user 0 {pkg}")
        if code == 0 and "Success" in out:
            removed.append(pkg)
            ok(desc)
        else:
            failed.append(pkg)
            err(f"{desc}: {out or 'ошибка'}")
    log_removed(adb.serial, removed)

    print()
    ok(f"Удалено: {len(removed)}" + (f", не удалось: {len(failed)}" if failed else ""))
    if removed:
        print(f"       Список сохранён в {REMOVED_LOG}")


def speed_up(adb, assume_yes=False):
    title("Ускорение")

    print("  1) Анимации интерфейса 0.5x (визуально телефон станет заметно быстрее)")
    results = [adb.shell(f"settings put global {key} 0.5")
               for key in ("window_animation_scale", "transition_animation_scale",
                           "animator_duration_scale")]
    if all(code == 0 and not out for code, out in results):
        ok("Анимации ускорены")
    else:
        err("Не получилось изменить настройки.")
        print("       Включите в «Для разработчиков» пункт «Отладка по USB (настройки")
        print("       безопасности)» — MIUI требует его для изменения настроек.")

    print("  2) Очистка кэша всех приложений")
    code, out = adb.shell("pm trim-caches 999G", timeout=300)
    if code == 0:
        ok("Кэш очищен")
    else:
        err(out)

    print("  3) Закрытие фоновых процессов")
    adb.shell("am kill-all")
    ok("Фоновые процессы закрыты")

    print("  4) Оптимизация (перекомпиляция) приложений")
    print("     Это главный пункт для «тормозящего с покупки» телефона: после")
    print("     обновлений приложения часто остаются неоптимизированными.")
    print("     Займёт 5–20 минут, телефон в это время может греться.")
    if ask_yes("Запустить оптимизацию?", default=True, assume_yes=assume_yes):
        print("     Идёт оптимизация, не отключайте телефон...")
        start = time.time()
        code, out = adb.shell("cmd package bg-dexopt-job", timeout=3600)
        minutes = (time.time() - start) / 60
        if code == 0:
            ok(f"Оптимизация завершена за {minutes:.0f} мин")
        else:
            err(f"Оптимизация завершилась с ошибкой: {out}")


def set_ad_block_dns(adb, enable, assume_yes=False):
    title("Блокировка рекламы через DNS")
    if enable:
        print(f"  Будет включён «Персональный DNS-сервер» {AD_BLOCK_DNS} (AdGuard).")
        print("  Он блокирует рекламу и трекеры во всех приложениях и браузерах,")
        print("  в том числе по мобильной сети. Отключить можно этим же меню или")
        print("  в Настройки → Подключение и общий доступ → Частный DNS-сервер.")
        if not ask_yes("Включить?", default=True, assume_yes=assume_yes):
            return
        r1 = adb.shell("settings put global private_dns_mode hostname")
        r2 = adb.shell(f"settings put global private_dns_specifier {AD_BLOCK_DNS}")
        results = [r1, r2]
    else:
        results = [adb.shell("settings put global private_dns_mode opportunistic")]
    if all(code == 0 and not out for code, out in results):
        ok("Готово" if enable else "Блокировка через DNS выключена")
    else:
        err("Не получилось изменить настройки.")
        print("       Включите «Отладка по USB (настройки безопасности)» в «Для разработчиков».")


def restore(adb):
    title("Восстановление удалённых приложений")
    removed = read_removed(adb.serial)
    current = adb.packages()
    removed = [p for p in removed if p not in current]
    if removed:
        print("  Удалены этой программой:")
        for i, pkg in enumerate(removed, 1):
            print(f"  {i:>3}. {pkg}")
        print("\n  Номера через пробел, «все» — вернуть всё, или имя пакета.")
    else:
        print("  В журнале нет удалённых приложений. Можно ввести имя пакета вручную.")
    raw = input("  > ").strip()
    if not raw:
        return
    if raw.lower() in ("все", "all", "dct"):
        targets = removed
    elif "." in raw:
        targets = raw.split()
    else:
        nums = {int(x) for x in raw.replace(",", " ").split() if x.isdigit()}
        targets = [p for i, p in enumerate(removed, 1) if i in nums]

    for pkg in targets:
        code, out = adb.shell(f"cmd package install-existing {pkg}")
        if code == 0 and "installed for user" in out:
            ok(pkg)
        else:
            err(f"{pkg}: {out or 'ошибка'}")


def auto(adb, assume_yes):
    remove_packages(adb, RECOMMENDED, "Удаление рекламы, трекеров и мусора", assume_yes)
    speed_up(adb, assume_yes)
    title("Готово")
    print("  Перезагрузите телефон, чтобы изменения применились полностью.")
    if ask_yes("Перезагрузить сейчас?", default=True, assume_yes=assume_yes):
        adb.run("reboot")
        ok("Телефон перезагружается")


def menu(adb):
    while True:
        title("Redmi Cleanup — главное меню")
        print("  1. Автоочистка: реклама + трекеры + мусор и ускорение (рекомендуется)")
        print("  2. Удалить рекламу, трекеры и мусор (без ускорения)")
        print("  3. Дополнительно: выбрать необязательные приложения для удаления")
        print("  4. Ускорение: анимации, кэш, оптимизация приложений")
        print("  5. Включить блокировку рекламы через DNS (AdGuard)")
        print("  6. Выключить блокировку рекламы через DNS")
        print("  7. Восстановить удалённые приложения")
        print("  8. Перезагрузить телефон")
        print("  0. Выход")
        choice = input("\n  Выберите пункт: ").strip()
        if choice == "1":
            auto(adb, assume_yes=False)
        elif choice == "2":
            remove_packages(adb, RECOMMENDED, "Удаление рекламы, трекеров и мусора")
        elif choice == "3":
            remove_packages(adb, OPTIONAL, "Необязательные приложения", pick=True)
        elif choice == "4":
            speed_up(adb)
        elif choice == "5":
            set_ad_block_dns(adb, enable=True)
        elif choice == "6":
            set_ad_block_dns(adb, enable=False)
        elif choice == "7":
            restore(adb)
        elif choice == "8":
            adb.run("reboot")
            ok("Телефон перезагружается")
        elif choice == "0":
            return


def main():
    parser = argparse.ArgumentParser(description="Очистка Xiaomi / Redmi от рекламы и мусора через ADB")
    parser.add_argument("--auto", action="store_true",
                        help="рекомендуемая очистка + ускорение без меню")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="не задавать вопросов (вместе с --auto)")
    parser.add_argument("--wifi", action="store_true",
                        help="подключиться к телефону по Wi-Fi (Android 11+)")
    args = parser.parse_args()

    title("Redmi Cleanup — очистка телефона от рекламы и мусора")
    print("  Приложения удаляются только для пользователя и всегда могут быть")
    print("  возвращены через пункт «Восстановить». Root не нужен, гарантия сохраняется.")

    adb_path = find_adb()
    if not adb_path:
        warn("ADB не найден.")
        if not ask_yes("Скачать ADB с сайта Google (~10 МБ)?", default=True, assume_yes=args.yes):
            return 1
        adb_path = download_adb()
        if not adb_path:
            return 1

    adb = Adb(adb_path)
    if not connect_device(adb, wifi=args.wifi):
        return 1
    show_device_info(adb)

    if args.auto:
        auto(adb, args.yes)
    else:
        menu(adb)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n  Прервано.")
        sys.exit(130)
