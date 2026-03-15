"""
CodeIntelligence — граф зависимостей + умный контекст + автотрекинг изменений.
Аналог vexp: строит карту кода, отслеживает изменения, выдаёт только релевантный контекст.
"""
import os
import json
import sqlite3
import hashlib
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field


@dataclass
class CodeSymbol:
    """Символ в коде: функция, класс, переменная."""
    name: str
    kind: str  # function, class, variable, import
    file_path: str
    line_start: int
    line_end: int
    signature: str = ""
    docstring: str = ""
    calls: List[str] = field(default_factory=list)      # что вызывает
    called_by: List[str] = field(default_factory=list)  # кем вызывается
    imports: List[str] = field(default_factory=list)    # что импортирует


@dataclass
class FileChange:
    """Изменение в файле."""
    file_path: str
    timestamp: datetime
    change_type: str  # added, modified, deleted
    symbols_added: List[str] = field(default_factory=list)
    symbols_removed: List[str] = field(default_factory=list)
    symbols_modified: List[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class RelevantContext:
    """Релевантный контекст для запроса."""
    symbols: List[CodeSymbol]
    related_files: List[str]
    recent_changes: List[FileChange]
    total_tokens_estimate: int
    relevance_scores: Dict[str, float]


class CodeIndexer:
    """Индексирует код и строит граф зависимостей."""

    # Паттерны для извлечения символов (без tree-sitter, на regex)
    PATTERNS = {
        'python': {
            'function': r'^(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)',
            'class': r'^class\s+(\w+)(?:\([^)]*\))?:',
            'import': r'^(?:from\s+([\w.]+)\s+)?import\s+([\w,\s.]+)',
            'call': r'(\w+)\s*\(',
            'variable': r'^(\w+)\s*=\s*',
        },
        'javascript': {
            'function': r'(?:async\s+)?function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>|(\w+)\s*:\s*(?:async\s+)?function',
            'class': r'class\s+(\w+)',
            'import': r'import\s+.*?\s+from\s+[\'"]([^\'"]+)[\'"]|require\s*\([\'"]([^\'"]+)[\'"]\)',
            'call': r'(\w+)\s*\(',
        }
    }

    def __init__(self, root_dir: str, db_path: str = None):
        self.root_dir = Path(root_dir)
        self.db_path = db_path or str(self.root_dir / ".code_index.db")
        self._init_db()
        self.symbols: Dict[str, CodeSymbol] = {}  # full_name -> symbol
        self.file_hashes: Dict[str, str] = {}      # file_path -> hash

    def _init_db(self):
        """Создаёт SQLite базу для хранения индекса."""
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS symbols (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                full_name TEXT UNIQUE NOT NULL,
                kind TEXT NOT NULL,
                file_path TEXT NOT NULL,
                line_start INTEGER,
                line_end INTEGER,
                signature TEXT,
                docstring TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS dependencies (
                id INTEGER PRIMARY KEY,
                from_symbol TEXT NOT NULL,
                to_symbol TEXT NOT NULL,
                dep_type TEXT NOT NULL,  -- calls, imports, inherits
                UNIQUE(from_symbol, to_symbol, dep_type)
            );

            CREATE TABLE IF NOT EXISTS file_hashes (
                file_path TEXT PRIMARY KEY,
                hash TEXT NOT NULL,
                indexed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS changes (
                id INTEGER PRIMARY KEY,
                file_path TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                change_type TEXT NOT NULL,
                symbols_json TEXT,
                summary TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_path);
            CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind);
            CREATE INDEX IF NOT EXISTS idx_deps_from ON dependencies(from_symbol);
            CREATE INDEX IF NOT EXISTS idx_deps_to ON dependencies(to_symbol);
        """)
        conn.commit()
        conn.close()

    def index_file(self, file_path: str) -> List[CodeSymbol]:
        """Индексирует один файл и возвращает найденные символы."""
        path = Path(file_path)
        if not path.exists():
            return []

        # Определяем язык
        ext = path.suffix.lower()
        if ext == '.py':
            lang = 'python'
        elif ext in ('.js', '.ts', '.jsx', '.tsx'):
            lang = 'javascript'
        else:
            return []

        # Читаем файл
        try:
            content = path.read_text(encoding='utf-8', errors='replace')
        except Exception:
            return []

        # Проверяем, изменился ли файл
        file_hash = hashlib.md5(content.encode()).hexdigest()
        if self.file_hashes.get(str(path)) == file_hash:
            return []  # Не изменился

        symbols = []
        patterns = self.PATTERNS.get(lang, {})
        lines = content.split('\n')

        current_class = None

        for i, line in enumerate(lines):
            line_num = i + 1
            stripped = line.strip()

            # Пропускаем комментарии и пустые строки
            if not stripped or stripped.startswith('#') or stripped.startswith('//'):
                continue

            # Ищем классы
            class_match = re.match(patterns.get('class', ''), stripped)
            if class_match:
                name = class_match.group(1)
                current_class = name

                symbols.append(CodeSymbol(
                    name=name,
                    kind='class',
                    file_path=str(path),
                    line_start=line_num,
                    line_end=line_num,  # Будет обновлено
                    signature=stripped,
                ))
                continue

            # Ищем функции
            func_match = re.match(patterns.get('function', ''), stripped)
            if func_match:
                name = func_match.group(1)
                if current_class:
                    full_name = f"{path.stem}.{current_class}.{name}"
                else:
                    full_name = f"{path.stem}.{name}"

                # Извлекаем вызовы внутри функции
                calls = self._extract_calls(content, line_num, patterns.get('call', ''))

                symbols.append(CodeSymbol(
                    name=name,
                    kind='function',
                    file_path=str(path),
                    line_start=line_num,
                    line_end=line_num,
                    signature=stripped,
                    calls=calls,
                ))
                continue

            # Ищем импорты
            import_match = re.match(patterns.get('import', ''), stripped)
            if import_match:
                groups = [g for g in import_match.groups() if g]
                if groups:
                    module = groups[0]
                    symbols.append(CodeSymbol(
                        name=module,
                        kind='import',
                        file_path=str(path),
                        line_start=line_num,
                        line_end=line_num,
                        signature=stripped,
                    ))

        # Сохраняем в БД
        self._save_symbols(symbols, str(path), file_hash)
        self.file_hashes[str(path)] = file_hash

        return symbols

    def _extract_calls(self, content: str, start_line: int, call_pattern: str) -> List[str]:
        """Извлекает вызовы функций из тела функции."""
        if not call_pattern:
            return []

        calls = set()
        lines = content.split('\n')
        indent_level = None

        for i in range(start_line, min(start_line + 50, len(lines))):
            line = lines[i]

            # Определяем уровень отступа функции
            if indent_level is None:
                indent_level = len(line) - len(line.lstrip())
                continue

            # Если вернулись на тот же или меньший отступ — конец функции
            current_indent = len(line) - len(line.lstrip())
            if line.strip() and current_indent <= indent_level:
                break

            # Ищем вызовы
            for match in re.finditer(call_pattern, line):
                call_name = match.group(1)
                # Фильтруем встроенные функции
                if call_name not in ('if', 'for', 'while', 'with', 'print', 'len', 'str', 'int', 'list', 'dict'):
                    calls.add(call_name)

        return list(calls)

    def _save_symbols(self, symbols: List[CodeSymbol], file_path: str, file_hash: str):
        """Сохраняет символы в БД."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Удаляем старые символы из этого файла
        cursor.execute("DELETE FROM symbols WHERE file_path = ?", (file_path,))
        cursor.execute("DELETE FROM dependencies WHERE from_symbol LIKE ?",
                       (f"{Path(file_path).stem}.%",))

        now = datetime.now().isoformat()

        for sym in symbols:
            full_name = f"{Path(file_path).stem}.{sym.name}"

            cursor.execute("""
                INSERT OR REPLACE INTO symbols
                (name, full_name, kind, file_path, line_start, line_end, signature, docstring, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (sym.name, full_name, sym.kind, file_path, sym.line_start, sym.line_end,
                  sym.signature, sym.docstring, now))

            # Сохраняем зависимости (вызовы)
            for call in sym.calls:
                cursor.execute("""
                    INSERT OR IGNORE INTO dependencies (from_symbol, to_symbol, dep_type)
                    VALUES (?, ?, 'calls')
                """, (full_name, call))

        # Обновляем хэш файла
        cursor.execute("""
            INSERT OR REPLACE INTO file_hashes (file_path, hash, indexed_at)
            VALUES (?, ?, ?)
        """, (file_path, file_hash, now))

        conn.commit()
        conn.close()

    def index_directory(self, extensions: List[str] = None) -> int:
        """Индексирует все файлы в директории."""
        if extensions is None:
            extensions = ['.py', '.js', '.ts']

        count = 0
        for ext in extensions:
            for file_path in self.root_dir.rglob(f"*{ext}"):
                # Пропускаем node_modules, venv, __pycache__
                if any(skip in str(file_path) for skip in ['node_modules', 'venv', '__pycache__', '.git']):
                    continue

                symbols = self.index_file(str(file_path))
                count += len(symbols)

        return count

    def get_symbol(self, name: str) -> Optional[CodeSymbol]:
        """Получает символ по имени."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT name, full_name, kind, file_path, line_start, line_end, signature, docstring
            FROM symbols WHERE name = ? OR full_name = ?
        """, (name, name))

        row = cursor.fetchone()
        conn.close()

        if row:
            return CodeSymbol(
                name=row[0],
                kind=row[2],
                file_path=row[3],
                line_start=row[4],
                line_end=row[5],
                signature=row[6],
                docstring=row[7],
            )
        return None

    def get_callers(self, symbol_name: str) -> List[str]:
        """Возвращает список функций, которые вызывают данный символ."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT from_symbol FROM dependencies
            WHERE to_symbol = ? OR to_symbol LIKE ?
        """, (symbol_name, f"%.{symbol_name}"))

        callers = [row[0] for row in cursor.fetchall()]
        conn.close()
        return callers

    def get_callees(self, symbol_name: str) -> List[str]:
        """Возвращает список функций, которые вызывает данный символ."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT to_symbol FROM dependencies
            WHERE from_symbol = ? OR from_symbol LIKE ?
        """, (symbol_name, f"%.{symbol_name}"))

        callees = [row[0] for row in cursor.fetchall()]
        conn.close()
        return callees

    def what_breaks_if_changed(self, symbol_name: str) -> List[str]:
        """Возвращает всё, что сломается при изменении символа."""
        affected = set()
        to_check = [symbol_name]
        checked = set()

        while to_check:
            current = to_check.pop()
            if current in checked:
                continue
            checked.add(current)

            callers = self.get_callers(current)
            for caller in callers:
                affected.add(caller)
                to_check.append(caller)

        return list(affected)


class ChangeTracker:
    """Отслеживает изменения в файлах и сохраняет их."""

    def __init__(self, indexer: CodeIndexer):
        self.indexer = indexer
        self.db_path = indexer.db_path

    def track_change(self, file_path: str, old_content: str = None, new_content: str = None) -> Optional[FileChange]:
        """Отслеживает изменение в файле и сохраняет его."""
        path = Path(file_path)

        # Определяем тип изменения
        if old_content is None and new_content:
            change_type = "added"
        elif old_content and new_content is None:
            change_type = "deleted"
        elif old_content and new_content:
            change_type = "modified"
        else:
            return None

        # Анализируем что изменилось
        old_symbols = self._extract_symbol_names(old_content) if old_content else set()
        new_symbols = self._extract_symbol_names(new_content) if new_content else set()

        added = new_symbols - old_symbols
        removed = old_symbols - new_symbols

        # Для модифицированных — нужно сравнить сигнатуры
        modified = []
        if change_type == "modified":
            # Упрощённо: считаем модифицированным если есть изменения в файле
            # В реальности нужно сравнивать AST
            pass

        # Генерируем summary
        summary_parts = []
        if added:
            summary_parts.append(f"добавлены: {', '.join(list(added)[:5])}")
        if removed:
            summary_parts.append(f"удалены: {', '.join(list(removed)[:5])}")
        if modified:
            summary_parts.append(f"изменены: {', '.join(modified[:5])}")

        summary = "; ".join(summary_parts) if summary_parts else f"файл {change_type}"

        change = FileChange(
            file_path=str(path),
            timestamp=datetime.now(),
            change_type=change_type,
            symbols_added=list(added),
            symbols_removed=list(removed),
            symbols_modified=modified,
            summary=summary,
        )

        # Сохраняем в БД
        self._save_change(change)

        # Переиндексируем файл
        if new_content:
            self.indexer.index_file(file_path)

        return change

    def _extract_symbol_names(self, content: str) -> Set[str]:
        """Извлекает имена символов из содержимого."""
        symbols = set()

        # Функции
        for match in re.finditer(r'(?:async\s+)?def\s+(\w+)', content):
            symbols.add(match.group(1))

        # Классы
        for match in re.finditer(r'class\s+(\w+)', content):
            symbols.add(match.group(1))

        return symbols

    def _save_change(self, change: FileChange):
        """Сохраняет изменение в БД."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        symbols_json = json.dumps({
            "added": change.symbols_added,
            "removed": change.symbols_removed,
            "modified": change.symbols_modified,
        })

        cursor.execute("""
            INSERT INTO changes (file_path, timestamp, change_type, symbols_json, summary)
            VALUES (?, ?, ?, ?, ?)
        """, (change.file_path, change.timestamp.isoformat(), change.change_type,
               symbols_json, change.summary))

        conn.commit()
        conn.close()

    def get_recent_changes(self, limit: int = 20) -> List[FileChange]:
        """Возвращает последние изменения."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT file_path, timestamp, change_type, symbols_json, summary
            FROM changes ORDER BY timestamp DESC LIMIT ?
        """, (limit,))

        changes = []
        for row in cursor.fetchall():
            symbols = json.loads(row[3]) if row[3] else {}
            changes.append(FileChange(
                file_path=row[0],
                timestamp=datetime.fromisoformat(row[1]),
                change_type=row[2],
                symbols_added=symbols.get("added", []),
                symbols_removed=symbols.get("removed", []),
                symbols_modified=symbols.get("modified", []),
                summary=row[4],
            ))

        conn.close()
        return changes


class ContextBuilder:
    """Строит релевантный контекст для запроса."""

    def __init__(self, indexer: CodeIndexer, tracker: ChangeTracker):
        self.indexer = indexer
        self.tracker = tracker

    def build_context(
        self,
        query: str,
        max_tokens: int = 3000,
        include_changes: bool = True
    ) -> RelevantContext:
        """
        Строит релевантный контекст для запроса.

        Вместо всех 18K токенов кода — только релевантные ~2-3K.
        """
        # Извлекаем ключевые слова из запроса
        keywords = self._extract_keywords(query)

        # Ищем релевантные символы
        relevant_symbols = []
        relevance_scores = {}

        conn = sqlite3.connect(self.indexer.db_path)
        cursor = conn.cursor()

        for keyword in keywords:
            cursor.execute("""
                SELECT name, full_name, kind, file_path, line_start, line_end, signature, docstring
                FROM symbols
                WHERE name LIKE ? OR full_name LIKE ? OR signature LIKE ?
                LIMIT 20
            """, (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"))

            for row in cursor.fetchall():
                symbol = CodeSymbol(
                    name=row[0],
                    kind=row[2],
                    file_path=row[3],
                    line_start=row[4],
                    line_end=row[5],
                    signature=row[6],
                    docstring=row[7],
                )

                # Считаем релевантность
                score = self._calculate_relevance(symbol, keywords)
                full_name = row[1]

                if full_name not in relevance_scores or score > relevance_scores[full_name]:
                    relevance_scores[full_name] = score
                    relevant_symbols.append(symbol)

        conn.close()

        # Добавляем связанные символы (что вызывают / кем вызываются)
        expanded_symbols = []
        for sym in relevant_symbols[:10]:  # Топ-10 по релевантности
            expanded_symbols.append(sym)

            # Добавляем callers
            callers = self.indexer.get_callers(sym.name)

            for caller in callers[:3]:
                caller_sym = self.indexer.get_symbol(caller)
                if caller_sym:
                    expanded_symbols.append(caller_sym)

        # Убираем дубликаты
        seen = set()
        unique_symbols = []
        for sym in expanded_symbols:
            key = f"{sym.file_path}:{sym.name}"
            if key not in seen:
                seen.add(key)
                unique_symbols.append(sym)

        # Собираем файлы
        related_files = list(set(sym.file_path for sym in unique_symbols))

        # Получаем недавние изменения если нужно
        recent_changes = []
        if include_changes:
            recent_changes = self.tracker.get_recent_changes(10)

        # Оцениваем токены
        tokens_estimate = sum(len(sym.signature) // 4 for sym in unique_symbols)
        tokens_estimate += sum(len(c.summary) // 4 for c in recent_changes)

        return RelevantContext(
            symbols=unique_symbols[:max_tokens // 100],  # Грубая оценка
            related_files=related_files,
            recent_changes=recent_changes,
            total_tokens_estimate=tokens_estimate,
            relevance_scores=relevance_scores,
        )

    def _extract_keywords(self, query: str) -> List[str]:
        """Извлекает ключевые слова из запроса."""
        # Убираем стоп-слова
        stop_words = {'в', 'на', 'и', 'или', 'что', 'как', 'где', 'the', 'a', 'an', 'is', 'are', 'to', 'for'}

        words = re.findall(r'\w+', query.lower())
        keywords = [w for w in words if w not in stop_words and len(w) > 2]

        # Добавляем CamelCase / snake_case токены
        for match in re.finditer(r'[A-Z][a-z]+|[a-z]+(?=[A-Z])|[a-z]+', query):
            word = match.group().lower()
            if word not in keywords and len(word) > 2:
                keywords.append(word)

        return keywords

    def _calculate_relevance(self, symbol: CodeSymbol, keywords: List[str]) -> float:
        """Вычисляет релевантность символа к ключевым словам."""
        score = 0.0
        name_lower = symbol.name.lower()
        sig_lower = symbol.signature.lower()

        for keyword in keywords:
            if keyword in name_lower:
                score += 1.0  # Точное совпадение в имени
            elif keyword in sig_lower:
                score += 0.5  # Совпадение в сигнатуре

        # Бонус за тип
        if symbol.kind == 'function':
            score *= 1.2
        elif symbol.kind == 'class':
            score *= 1.1

        return score

    def format_for_llm(self, context: RelevantContext) -> str:
        """Форматирует контекст для отправки в LLM."""
        parts = []

        # Релевантные символы
        if context.symbols:
            parts.append("=== РЕЛЕВАНТНЫЙ КОД ===")
            for sym in context.symbols[:15]:
                parts.append(f"\n[{sym.kind}] {sym.name}")
                parts.append(f"  Файл: {sym.file_path}:{sym.line_start}")
                parts.append(f"  {sym.signature}")
                if sym.docstring:
                    parts.append(f"  Описание: {sym.docstring[:100]}")

        # Недавние изменения
        if context.recent_changes:
            parts.append("\n=== НЕДАВНИЕ ИЗМЕНЕНИЯ ===")
            for change in context.recent_changes[:5]:
                parts.append(f"  [{change.timestamp.strftime('%H:%M')}] {change.file_path}: {change.summary}")

        # Связанные файлы
        if context.related_files:
            parts.append(f"\n=== СВЯЗАННЫЕ ФАЙЛЫ ({len(context.related_files)}) ===")
            parts.append("  " + ", ".join(Path(f).name for f in context.related_files[:10]))

        parts.append(f"\n[Контекст: ~{context.total_tokens_estimate} токенов]")

        return "\n".join(parts)


class CodeIntelligence:
    """Главный класс — объединяет индексатор, трекер и контекст-билдер."""

    def __init__(self, root_dir: str, db_path: str = None):
        self.root_dir = Path(root_dir)
        self.indexer = CodeIndexer(root_dir, db_path)
        self.tracker = ChangeTracker(self.indexer)
        self.context_builder = ContextBuilder(self.indexer, self.tracker)

        # File watcher (если установлен watchdog)
        self._watcher = None
        self._watcher_thread = None

    def index_all(self) -> int:
        """Индексирует весь проект."""
        return self.indexer.index_directory()

    def get_context_for_query(self, query: str, max_tokens: int = 3000) -> str:
        """Возвращает релевантный контекст для запроса."""
        context = self.context_builder.build_context(query, max_tokens)
        return self.context_builder.format_for_llm(context)

    def on_file_changed(self, file_path: str, old_content: str = None, new_content: str = None):
        """Вызывается при изменении файла."""
        change = self.tracker.track_change(file_path, old_content, new_content)
        if change:
            print(f"  [CodeIntelligence] Tracked: {change.summary}")

    def what_breaks(self, symbol_name: str) -> List[str]:
        """Что сломается при изменении символа."""
        return self.indexer.what_breaks_if_changed(symbol_name)

    def start_watching(self):
        """Запускает отслеживание изменений файлов."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class Handler(FileSystemEventHandler):
                def __init__(self, intelligence):
                    self.intelligence = intelligence
                    self._file_contents = {}

                def on_modified(self, event):
                    if event.is_directory:
                        return
                    if event.src_path.endswith(('.py', '.js', '.ts')):
                        try:
                            new_content = Path(event.src_path).read_text(encoding='utf-8')
                            old_content = self._file_contents.get(event.src_path)
                            self.intelligence.on_file_changed(event.src_path, old_content, new_content)
                            self._file_contents[event.src_path] = new_content
                        except Exception:
                            pass

            self._watcher = Observer()
            handler = Handler(self)
            self._watcher.schedule(handler, str(self.root_dir), recursive=True)
            self._watcher.start()
            print(f"  [CodeIntelligence] Watching {self.root_dir}")

        except ImportError:
            print("  [CodeIntelligence] watchdog not installed, file watching disabled")

    def stop_watching(self):
        """Останавливает отслеживание."""
        if self._watcher:
            self._watcher.stop()
            self._watcher.join()
