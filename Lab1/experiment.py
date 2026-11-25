import argparse
import csv
import os
from pathlib import Path
import platform
import re
import statistics
import subprocess
import sys

DEFAULT_SIZES = [200, 400, 800, 1200, 1600, 2000]
START_MARKER = "<!-- RESULTS_START -->"
END_MARKER = "<!-- RESULTS_END -->"

parser = argparse.ArgumentParser(
    description="Эксперименты по последовательному умножению квадратных матриц"
)
parser.add_argument(
    "--exe",
    default="matrix.exe" if os.name == "nt" else "./matrix",
    help="путь к скомпилированной программе",
)
parser.add_argument(
    "--sizes", type=int, nargs="+", default=DEFAULT_SIZES,
    help="размеры квадратных матриц",
)
parser.add_argument(
    "--repeats", type=int, default=3,
    help="количество повторов для каждого размера (по умолчанию: 3)",
)
args = parser.parse_args()

if args.repeats < 1 or any(n < 1 for n in args.sizes):
    parser.error("Размеры матриц и количество повторов должны быть положительными")

results_dir = Path("results")
results_dir.mkdir(exist_ok=True)
csv_path = results_dir / "results.csv"


def save_csv(rows):
    """Сохраняет уже полученные строки, чтобы результаты не терялись при сбое."""
    fieldnames = ["N", "time_sec", "operations", "memory_bytes", "verified", "repeats"]
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


rows = []
for n in args.sizes:
    subprocess.run([sys.executable, "generate.py", str(n)], check=True)

    times = []
    for repeat in range(1, args.repeats + 1):
        process = subprocess.run(
            [args.exe], check=True, capture_output=True, text=True
        )
        match = re.search(r"time_sec=([0-9]+(?:\.[0-9]+)?)", process.stdout)
        if match is None:
            raise RuntimeError(
                "Не удалось прочитать время из вывода программы:\n" + process.stdout
            )
        elapsed = float(match.group(1))
        times.append(elapsed)
        print(
            f"N={n}, повтор {repeat}/{args.repeats}: {elapsed:.6f} с",
            flush=True,
        )

    subprocess.run([sys.executable, "check.py"], check=True)
    average_time = statistics.mean(times)
    rows.append(
        {
            "N": n,
            "time_sec": f"{average_time:.6f}",
            "operations": 2 * n**3,
            "memory_bytes": 3 * n * n * 8,
            "verified": "PASS",
            "repeats": args.repeats,
        }
    )
    save_csv(rows)

    # Построение графика после каждого завершённого размера сохраняет актуальные
    # результаты даже в случае, если следующий эксперимент не завершится.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.figure(figsize=(8, 4.8))
    plt.plot(
        [int(row["N"]) for row in rows],
        [float(row["time_sec"]) for row in rows],
        marker="o",
    )
    plt.title("Последовательное умножение матриц")
    plt.xlabel("Размер матрицы N")
    plt.ylabel("Время умножения, с")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(results_dir / "time_vs_size.png", dpi=160)
    plt.close()

    print(f"Промежуточные результаты сохранены: N={n}", flush=True)


# Формируем отчёт только после успешного завершения всех заданных размеров.
report_path = Path("README.md")
report_text = report_path.read_text(encoding="utf-8")
if START_MARKER not in report_text or END_MARKER not in report_text:
    raise RuntimeError("В README.md не найдены маркеры RESULTS_START / RESULTS_END")

header = (
    "| N | Среднее время, с | Повторов | Операций (оценка) | "
    "Память трёх матриц, байт | Проверка |\n"
    "|---:|---:|---:|---:|---:|:---:|\n"
)
rows_table = "".join(
    f'| {row["N"]} | {float(row["time_sec"]):.6f} | {row["repeats"]} | '
    f'{row["operations"]} | {row["memory_bytes"]} | {row["verified"]} |\n'
    for row in rows
)
source_header = (
    "| Размер матрицы N | Время, с (данные для графика) |\n"
    "|---:|---:|\n"
)
source_rows = "".join(
    f'| {row["N"]} | {float(row["time_sec"]):.6f} |\n'
    for row in rows
)

cpu_model = "не удалось определить"
try:
    cpuinfo = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="ignore")
    for line in cpuinfo.splitlines():
        if line.lower().startswith("model name"):
            cpu_model = line.split(":", 1)[1].strip()
            break
except OSError:
    pass

conditions = (
    f"**Условия измерений:** {platform.platform()}; процессор: {cpu_model}; "
    f"доступно логических CPU: {os.cpu_count()}; Python {platform.python_version()}. "
    f"Для каждого размера выполнено {args.repeats} запуск(а/ов); в таблице указано "
    "среднее время. Время измерено внутри C++-программы только для умножения, "
    "без чтения и записи файлов. Компиляция выполнялась отдельно.\n\n"
)
conclusion = (
    "\n**Вывод по эксперименту:** при увеличении размера матриц время вычислений "
    "возрастает. Это согласуется с теоретической оценкой сложности алгоритма O(N³). "
    "Проверка каждого результата выполнена независимо с помощью NumPy и завершилась "
    "успешно. Полученные времена относятся к указанной выше вычислительной среде; "
    "на другом компьютере они могут отличаться.\n"
)
block = (
    conditions
    + "### Результаты измерений\n\n"
    + header + rows_table
    + "\n### Исходные данные для графика\n\n"
    + "Для построения графика использованы следующие пары значений: размер матрицы N "
    "и среднее фактическое время умножения.\n\n"
    + source_header + source_rows
    + "\n### График зависимости времени от размера матрицы\n\n"
    + "![График времени выполнения](results/time_vs_size.png)\n"
    + conclusion
)

start_index = report_text.index(START_MARKER) + len(START_MARKER)
end_index = report_text.index(END_MARKER)
updated_report = (
    report_text[:start_index] + "\n\n" + block + "\n" + report_text[end_index:]
)
report_path.write_text(updated_report, encoding="utf-8")
print("Готово: README.md, results/results.csv и results/time_vs_size.png обновлены.")
