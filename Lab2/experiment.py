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


def default_thread_counts():
    """Возвращает уровни 1, 2, 4, 8 в пределах доступных логических CPU."""
    cpu_count = os.cpu_count() or 1
    upper_limit = min(cpu_count, 8)
    counts = [count for count in (1, 2, 4, 8) if count <= upper_limit]
    if upper_limit not in counts and upper_limit > 1:
        counts.append(upper_limit)
    return counts


parser = argparse.ArgumentParser(
    description="Эксперименты по последовательному и OpenMP-умножению матриц"
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
    "--threads", type=int, nargs="+", default=None,
    help="количество нитей OpenMP; по умолчанию: 1, 2, 4 и 8 (с учётом CPU)",
)
parser.add_argument(
    "--repeats", type=int, default=3,
    help="количество повторов каждой конфигурации (по умолчанию: 3)",
)
args = parser.parse_args()

thread_counts = args.threads if args.threads is not None else default_thread_counts()
thread_counts = sorted(set(thread_counts))
if args.repeats < 1 or any(n < 1 for n in args.sizes):
    parser.error("Размеры матриц и количество повторов должны быть положительными")
if not thread_counts or any(count < 1 for count in thread_counts):
    parser.error("Количество нитей должно быть положительным")

root = Path(__file__).resolve().parent
results_dir = root / "results"
results_dir.mkdir(exist_ok=True)
csv_path = results_dir / "results.csv"
result_path = root / "result.txt"

FIELDNAMES = [
    "N", "mode", "threads", "mean_time_sec", "min_time_sec",
    "speedup", "efficiency_percent", "repeats", "verified",
]
rows = []


def run_checked(command):
    process = subprocess.run(
        command,
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return process.stdout


def run_configuration(executable, mode, threads, n):
    times = []
    for repeat in range(1, args.repeats + 1):
        stdout = run_checked([
            executable,
            "--mode", mode,
            "--threads", str(threads),
            "--output", str(result_path),
        ])
        match = re.search(r"time_sec=([0-9]+(?:\.[0-9]+)?(?:[eE][+-]?\d+)?)", stdout)
        if match is None:
            raise RuntimeError("Не удалось прочитать время из вывода программы:\n" + stdout)
        elapsed = float(match.group(1))
        times.append(elapsed)
        print(
            f"N={n}, режим={mode}, нитей={threads}, "
            f"повтор {repeat}/{args.repeats}: {elapsed:.6f} с",
            flush=True,
        )
    return times


def verify_result():
    output = run_checked([
        sys.executable,
        str(root / "check.py"),
        "--result", str(result_path),
    ])
    print(output.strip(), flush=True)


def save_csv():
    with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def save_graphs():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    parallel_rows = [row for row in rows if row["mode"] == "parallel"]
    sizes = sorted({int(row["N"]) for row in rows})
    thread_values = sorted({int(row["threads"]) for row in parallel_rows})

    # График 1: время параллельного умножения в зависимости от числа нитей.
    plt.figure(figsize=(9, 5.5))
    for n in sizes:
        selected = sorted(
            (row for row in parallel_rows if int(row["N"]) == n),
            key=lambda row: int(row["threads"]),
        )
        if selected:
            plt.plot(
                [int(row["threads"]) for row in selected],
                [float(row["mean_time_sec"]) for row in selected],
                marker="o", label=f"N={n}",
            )
    plt.xlabel("Количество нитей OpenMP")
    plt.ylabel("Среднее время, с")
    plt.title("Время параллельного умножения от числа нитей")
    plt.xticks(thread_values)
    plt.grid(True, alpha=0.3)
    if plt.gca().get_legend_handles_labels()[0]:
        plt.legend(title="Размер матрицы")
    plt.tight_layout()
    plt.savefig(results_dir / "time_by_threads.png", dpi=160)
    plt.close()

    # График 2: ускорение относительно последовательной реализации.
    plt.figure(figsize=(9, 5.5))
    for n in sizes:
        selected = sorted(
            (row for row in parallel_rows if int(row["N"]) == n),
            key=lambda row: int(row["threads"]),
        )
        if selected:
            plt.plot(
                [int(row["threads"]) for row in selected],
                [float(row["speedup"]) for row in selected],
                marker="o", label=f"N={n}",
            )
    if thread_values:
        plt.plot(thread_values, thread_values, linestyle="--", label="Идеальное ускорение")
    plt.xlabel("Количество нитей OpenMP")
    plt.ylabel("Ускорение S = Tпосл / Tпаралл")
    plt.title("Ускорение параллельного умножения")
    plt.xticks(thread_values)
    plt.grid(True, alpha=0.3)
    if plt.gca().get_legend_handles_labels()[0]:
        plt.legend(title="Размер матрицы")
    plt.tight_layout()
    plt.savefig(results_dir / "speedup.png", dpi=160)
    plt.close()

    # График 3: сравнение последовательного и параллельных вариантов по размерам.
    plt.figure(figsize=(9, 5.5))
    sequential_rows = [row for row in rows if row["mode"] == "sequential"]
    if sequential_rows:
        sequential_rows.sort(key=lambda row: int(row["N"]))
        plt.plot(
            [int(row["N"]) for row in sequential_rows],
            [float(row["mean_time_sec"]) for row in sequential_rows],
            marker="o", linestyle="--", label="Последовательно",
        )
    for threads in thread_values:
        selected = sorted(
            (row for row in parallel_rows if int(row["threads"]) == threads),
            key=lambda row: int(row["N"]),
        )
        if selected:
            plt.plot(
                [int(row["N"]) for row in selected],
                [float(row["mean_time_sec"]) for row in selected],
                marker="o", label=f"OpenMP: {threads} нит.",
            )
    plt.xlabel("Размер матрицы N")
    plt.ylabel("Среднее время, с")
    plt.title("Время выполнения для разных размеров матриц")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(results_dir / "time_by_size.png", dpi=160)
    plt.close()


def update_readme():
    readme_path = root / "README.md"
    report_text = readme_path.read_text(encoding="utf-8")
    if START_MARKER not in report_text or END_MARKER not in report_text:
        raise RuntimeError("В README.md не найдены маркеры RESULTS_START / RESULTS_END")

    cpu_model = platform.processor() or platform.machine() or "не удалось определить"
    cpu_count = os.cpu_count() or 1
    conditions = (
        f"**Условия измерений:** {platform.platform()}; процессор: {cpu_model}; "
        f"логических CPU: {cpu_count}; Python {platform.python_version()}. "
        f"Размеры: {', '.join(map(str, args.sizes))}; количество нитей OpenMP: "
        f"{', '.join(map(str, thread_counts))}; повторов на конфигурацию: {args.repeats}. "
        "Время измерено внутри C++-программы только для умножения матриц, без чтения "
        "и записи файлов. Компиляция выполнялась отдельно.\n\n"
    )

    table_header = (
        "| N | Режим | Нити | Среднее время, с | Мин. время, с | "
        "Ускорение | Эффективность, % | Проверка |\n"
        "|---:|:---|---:|---:|---:|---:|---:|:---:|\n"
    )
    table_rows = ""
    for row in rows:
        speedup = f'{float(row["speedup"]):.3f}'
        efficiency = "—" if row["efficiency_percent"] == "" else f'{float(row["efficiency_percent"]):.1f}'
        mode_label = "Последовательно" if row["mode"] == "sequential" else "OpenMP"
        table_rows += (
            f'| {row["N"]} | {mode_label} | {row["threads"]} | '
            f'{float(row["mean_time_sec"]):.6f} | {float(row["min_time_sec"]):.6f} | '
            f'{speedup} | {efficiency} | {row["verified"]} |\n'
        )

    conclusion = (
        "\n### Графики\n\n"
        "**Время параллельного умножения в зависимости от числа нитей:**\n\n"
        "![Время от числа нитей](results/time_by_threads.png)\n\n"
        "**Ускорение относительно последовательной реализации:**\n\n"
        "![Ускорение](results/speedup.png)\n\n"
        "**Время выполнения для разных размеров матриц:**\n\n"
        "![Время от размера матрицы](results/time_by_size.png)\n\n"
        "**Вывод:** ускорение и эффективность зависят от размера матрицы и числа "
        "нитей. При небольших размерах накладные расходы на создание и координацию "
        "нитей могут уменьшать выигрыш. Для крупных матриц параллельная обработка "
        "может сократить время вычислений; фактический результат определяется "
        "характеристиками процессора и измерениями на данном компьютере.\n"
    )

    block = (
        conditions
        + "### Таблица результатов экспериментов\n\n"
        + "Последовательный вариант используется как базовый. Ускорение рассчитано "
        "по формуле S = Tпосл / Tпаралл; эффективность — E = S / p × 100%, где p — "
        "число нитей OpenMP. Проверка PASS означает совпадение результата с "
        "независимым вычислением NumPy.\n\n"
        + table_header + table_rows
        + conclusion
    )

    start_index = report_text.index(START_MARKER) + len(START_MARKER)
    end_index = report_text.index(END_MARKER)
    updated = report_text[:start_index] + "\n\n" + block + "\n" + report_text[end_index:]
    readme_path.write_text(updated, encoding="utf-8")


exe_path = args.exe
if os.name != "nt" and not Path(exe_path).is_absolute():
    exe_path = str((root / exe_path).resolve())
elif os.name == "nt" and ("\\" not in exe_path and "/" not in exe_path):
    exe_path = str((root / exe_path).resolve())

if not Path(exe_path).exists():
    raise SystemExit(f"Не найден исполняемый файл: {exe_path}. Сначала скомпилируйте main.cpp.")

print(f"Размеры матриц: {args.sizes}")
print(f"Количество нитей OpenMP: {thread_counts}")
print(f"Повторов на конфигурацию: {args.repeats}")
print(f"Логических CPU: {os.cpu_count()}")

for n in args.sizes:
    print(f"\n=== Матрицы {n} x {n} ===", flush=True)
    run_checked([sys.executable, str(root / "generate.py"), str(n)])

    sequential_times = run_configuration(exe_path, "sequential", 1, n)
    verify_result()
    sequential_mean = statistics.mean(sequential_times)
    rows.append({
        "N": n,
        "mode": "sequential",
        "threads": 1,
        "mean_time_sec": f"{sequential_mean:.9f}",
        "min_time_sec": f"{min(sequential_times):.9f}",
        "speedup": "1.000000",
        "efficiency_percent": "",
        "repeats": args.repeats,
        "verified": "PASS",
    })
    save_csv()
    save_graphs()

    for threads in thread_counts:
        parallel_times = run_configuration(exe_path, "parallel", threads, n)
        verify_result()
        parallel_mean = statistics.mean(parallel_times)
        speedup = sequential_mean / parallel_mean if parallel_mean > 0 else 0.0
        efficiency = speedup / threads * 100.0
        rows.append({
            "N": n,
            "mode": "parallel",
            "threads": threads,
            "mean_time_sec": f"{parallel_mean:.9f}",
            "min_time_sec": f"{min(parallel_times):.9f}",
            "speedup": f"{speedup:.9f}",
            "efficiency_percent": f"{efficiency:.6f}",
            "repeats": args.repeats,
            "verified": "PASS",
        })
        save_csv()
        save_graphs()
        print(
            f"Сохранено: N={n}, нитей={threads}, ускорение={speedup:.3f}, "
            f"эффективность={efficiency:.1f}%",
            flush=True,
        )

    update_readme()
    print(f"Результаты для N={n} сохранены в CSV и README.", flush=True)

print("\nЭксперименты завершены.")
print("Файлы: results/results.csv, results/time_by_threads.png, results/speedup.png, results/time_by_size.png")
