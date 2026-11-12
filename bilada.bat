@echo off
chcp 65001 >nul
echo ========================================
echo    СБОРКА HOI4 FOCUS & IDEA EDITOR v1.0
echo ========================================

echo Проверка расположения...
if not exist "hoi4_editor.py" (
    echo.
    echo ❌ ОШИБКА: Файл hoi4_editor.py не найден в текущей папке!
    echo.
    echo 📁 Переместите этот bat-файл в папку с hoi4_editor.py
    echo 💡 Или откройте командную строку в папке с кодом и запустите этот bat-файл
    echo.
    pause
    exit /b 1
)

echo.
echo Проверка наличия иконки...
if not exist "icon_hoi4.ico" (
    echo.
    echo ⚠️ ВНИМАНИЕ: Файл иконки icon_hoi4.ico не найден!
    echo Будет использована стандартная иконка.
    echo.
    set ICON_OPTION=--icon=NONE
) else (
    echo ✅ Иконка найдена: icon_hoi4.ico
    set ICON_OPTION=--icon=icon_hoi4.ico
)

echo.
echo Проверка Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден! Установите Python 3.8 или выше.
    echo    Скачать: https://www.python.org/downloads/
    pause
    exit /b 1
)
python --version

echo.
echo Установка и обновление зависимостей...
pip install --upgrade pip --quiet
pip install PyInstaller --quiet

echo.
echo Очистка предыдущих сборок...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "__pycache__" rmdir /s /q "__pycache__"
if exist "HOI4_Editor.spec" del "HOI4_Editor.spec"
if exist "hoi4_editor.spec" del "hoi4_editor.spec"

echo.
echo Проверка доступности библиотек...
python -c "import tkinter; print('✅ Tkinter доступен')" || echo ❌ Ошибка Tkinter
python -c "import json; print('✅ JSON доступен')" || echo ❌ Ошибка JSON
python -c "import re; print('✅ re доступен')" || echo ❌ Ошибка re
python -c "import shutil; print('✅ shutil доступен')" || echo ❌ Ошибка shutil

echo.
echo Сборка EXE версии 1.0...
python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name "HOI4_Editor" ^
    %ICON_OPTION% ^
    --hidden-import=tkinter ^
    --hidden-import=tkinter.ttk ^
    --hidden-import=tkinter.filedialog ^
    --hidden-import=tkinter.messagebox ^
    --hidden-import=tkinter.simpledialog ^
    --hidden-import=json ^
    --hidden-import=re ^
    --hidden-import=os ^
    --hidden-import=sys ^
    --hidden-import=shutil ^
    --clean ^
    hoi4_editor.py

if exist "dist\HOI4_Editor.exe" (
    echo.
    echo ========================================
    echo    ✅ УСПЕХ! HOI4 Editor v1.0 создан!
    echo ========================================
    echo.
    echo 📁 Файл: dist\HOI4_Editor.exe
    echo 🖼️  Иконка: %ICON_OPTION%
    echo 📏 Размер:
    forfiles /p "dist" /m "HOI4_Editor.exe" /c "cmd /c echo   @fsize bytes"
    echo.
    echo ========================================
    echo    🚀 ВОЗМОЖНОСТИ РЕДАКТОРА
    echo ========================================
    echo.
    echo 🌳 ФОКУСЫ:
    echo    • Визуальный редактор дерева фокусов с drag-and-drop
    echo    • Соединение фокусов стрелками (prerequisite)
    echo    • Свойства: ID, название, иконка, стоимость, координаты
    echo    • Быстрые кнопки эффектов (политвласть, стабильность и т.д.)
    echo    • Удаление правым кликом по фокусу
    echo.
    echo 💡 ИДЕИ:
    echo    • Нацдухи, советники, дизайнеры, теоретики, главы штабов
    echo    • Категории: country, law, political_advisor, army_chief и др.
    echo    • Модификаторы с кнопками быстрой вставки
    echo    • Условия allowed / available / visible
    echo    • Стоимость удаления, картинки из ванилы
    echo.
    echo 📤 ЭКСПОРТ:
    echo    • Готовый мод: папка + .mod-файл
    echo    • common/national_focus/*.txt — дерево фокусов
    echo    • common/ideas/*.txt — идеи
    echo    • localisation/russian/*.yml — русская локализация
    echo    • descriptor.mod + .mod для лаунчера
    echo.
    echo 💾 ПРОЕКТ:
    echo    • Ctrl+S — сохранить в .json (можно продолжить позже)
    echo    • Ctrl+O — открыть сохранённый проект
    echo    • Ctrl+E — быстрый экспорт мода
    echo.
    echo 💡 ПОДСКАЗКИ:
    echo    • Всплывающие подсказки при наведении на любую кнопку
    echo    • Синяя строка внизу с подсказкой по текущему действию
    echo    • Кнопка "❓ Инструкция" — пошаговый гайд
    echo.
    echo ========================================
    echo    ⚠️  ВАЖНАЯ ИНФОРМАЦИЯ
    echo ========================================
    echo.
    echo 1. Редактор НЕ требует установленного Hearts of Iron IV
    echo 2. Экспортированный мод копируйте в:
    echo    Documents\Paradox Interactive\Hearts of Iron IV\mod\
    echo 3. Затем включите мод в лаунчере игры
    echo 4. Если дерево не появляется — увеличьте "Приоритет (factor)"
    echo    в настройках мода (например, до 1000)
    echo 5. Сохраняйте проект в .json для продолжения работы
    echo.
    echo ========================================
    echo    🚀 ЗАПУСК ПРОГРАММЫ
    echo ========================================
    echo.
    echo Чтобы запустить программу, откройте папку "dist" и запустите:
    echo "HOI4_Editor.exe"
    echo.
    echo Или нажмите любую клавишу для автоматического запуска...
    echo.
    pause

    REM Автоматический запуск программы
    start "" "dist\HOI4_Editor.exe"

) else (
    echo.
    echo ========================================
    echo    ❌ ОШИБКА СБОРКИ
    echo ========================================
    echo.
    echo Пробуем упрощенную сборку...
    echo.

    python -m PyInstaller --onefile --windowed %ICON_OPTION% hoi4_editor.py

    if exist "dist\hoi4_editor.exe" (
        echo.
        echo ✅ Сборка успешна (упрощенная версия)!
        echo 📁 Файл: dist\hoi4_editor.exe
        echo 💡 Переименуйте в: HOI4_Editor.exe
        echo 📏 Размер:
        forfiles /p "dist" /m "hoi4_editor.exe" /c "cmd /c echo   @fsize bytes"
        echo.
        echo Запуск программы...
        pause
        start "" "dist\hoi4_editor.exe"
    ) else (
        echo.
        echo ❌ КРИТИЧЕСКАЯ ОШИБКА СБОРКИ
        echo.
        echo ========================================
        echo    🔧 РЕШЕНИЕ ПРОБЛЕМ
        echo ========================================
        echo.
        echo 1. ПРОВЕРЬТЕ PYTHON:
        echo    python --version
        echo.
        echo 2. ОБНОВИТЕ PIP:
        echo    python -m pip install --upgrade pip
        echo.
        echo 3. УСТАНОВИТЕ PYINSTALLER ВРУЧНУЮ:
        echo    pip install PyInstaller
        echo.
        echo 4. ЗАПУСТИТЕ СКРИПТ НАПРЯМУЮ (для проверки):
        echo    python hoi4_editor.py
        echo.
        echo 5. ЕСЛИ ОШИБКА ПРО TCL/TK:
        echo    Переустановите Python с галочкой "tcl/tk and IDLE"
        echo.
        echo 6. ПРОВЕРЬТЕ ПУТИ:
        echo    Убедитесь, что Python добавлен в PATH
        echo.
        echo ========================================
        pause
        exit /b 1
    )
)

exit /b 0