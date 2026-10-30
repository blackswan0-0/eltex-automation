from pathlib import Path

path = Path("out") / "train" / "test.txt"

print("Полный путь: ", path.resolve())
print("Имя файла: ", path.name)
print("Расширение файла: ", path.suffix)
print("Папка родителя: ", path.parent)

path.parent.mkdir(parents=True, exist_ok=True)
path.write_text("привет", encoding="utf-8")

if path.exists():
    print("Файл существует")
    print(f"Размер файла: {path.stat().st_size} байт")
    print("-------Содержимое файла-------")
    print(path.read_text(encoding="utf-8"))
else:
    print("Файл не существует")
