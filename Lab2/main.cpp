#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <omp.h>

using namespace std;

class Matrix {
public:
    int n;
    vector<vector<double>> cells;

    explicit Matrix(int size) : n(size), cells(size, vector<double>(size, 0.0)) {}

    void load(ifstream& stream) {
        for (auto& row : cells) {
            for (double& number : row) {
                if (!(stream >> number)) {
                    throw runtime_error("Incorrect matrix data");
                }
            }
        }
    }

    // Последовательное умножение. Порядок i-k-j обеспечивает последовательный
    // доступ к элементам строк B и C в памяти.
    Matrix multiply_sequential(const Matrix& other) const {
        if (n != other.n) {
            throw runtime_error("Matrix sizes do not match");
        }

        Matrix answer(n);
        for (int i = 0; i < n; ++i) {
            for (int k = 0; k < n; ++k) {
                const double value = cells[i][k];
                for (int j = 0; j < n; ++j) {
                    answer.cells[i][j] += value * other.cells[k][j];
                }
            }
        }
        return answer;
    }

    // Параллельное умножение: каждая нить обрабатывает отдельные строки
    // результирующей матрицы, поэтому одновременной записи в одну ячейку нет.
    Matrix multiply_parallel(const Matrix& other, int thread_count) const {
        if (n != other.n) {
            throw runtime_error("Matrix sizes do not match");
        }
        if (thread_count < 1) {
            throw runtime_error("Thread count must be positive");
        }

        Matrix answer(n);
        #pragma omp parallel for num_threads(thread_count) schedule(static)
        for (int i = 0; i < n; ++i) {
            for (int k = 0; k < n; ++k) {
                const double value = cells[i][k];
                for (int j = 0; j < n; ++j) {
                    answer.cells[i][j] += value * other.cells[k][j];
                }
            }
        }
        return answer;
    }

    void save(ofstream& stream) const {
        stream << n << '\n' << setprecision(17);
        for (const auto& row : cells) {
            for (double number : row) {
                stream << number << ' ';
            }
            stream << '\n';
        }
    }
};

int main(int argc, char* argv[]) {
    try {
        string mode = "sequential";
        string output_path = "result.txt";
        int thread_count = 1;

        for (int i = 1; i < argc; ++i) {
            const string argument = argv[i];
            if (argument == "--mode" && i + 1 < argc) {
                mode = argv[++i];
            } else if (argument == "--threads" && i + 1 < argc) {
                thread_count = stoi(argv[++i]);
            } else if (argument == "--output" && i + 1 < argc) {
                output_path = argv[++i];
            } else if (argument == "--help") {
                cout << "Usage: matrix.exe [--mode sequential|parallel] [--threads N] [--output FILE]\n";
                return 0;
            } else {
                throw runtime_error("Unknown or incomplete argument: " + argument);
            }
        }

        if (mode != "sequential" && mode != "parallel") {
            throw runtime_error("Mode must be 'sequential' or 'parallel'");
        }
        if (thread_count < 1) {
            throw runtime_error("Thread count must be positive");
        }

        // Отключаем динамическое изменение числа нитей, чтобы эксперимент
        // запускал именно то количество, которое передано через --threads.
        omp_set_dynamic(0);

        ifstream first("A.txt"), second("B.txt");
        if (!first || !second) {
            throw runtime_error("Cannot open A.txt or B.txt");
        }

        int first_size = 0;
        int second_size = 0;
        if (!(first >> first_size) || !(second >> second_size) ||
            first_size <= 0 || first_size != second_size) {
            throw runtime_error("Cannot read matching matrix sizes");
        }

        Matrix a(first_size), b(first_size);
        a.load(first);
        b.load(second);

        const auto start = chrono::steady_clock::now();
        Matrix result = (mode == "sequential")
            ? a.multiply_sequential(b)
            : a.multiply_parallel(b, thread_count);
        const auto finish = chrono::steady_clock::now();

        ofstream output(output_path);
        if (!output) {
            throw runtime_error("Cannot open output file: " + output_path);
        }
        result.save(output);
        output.close();

        const double seconds = chrono::duration<double>(finish - start).count();
        const long long size = first_size;
        cout << fixed << setprecision(9)
             << "mode=" << mode
             << " threads=" << (mode == "sequential" ? 1 : thread_count)
             << " time_sec=" << seconds
             << " N=" << first_size
             << " operations=" << 2LL * size * size * size
             << " memory_bytes=" << 3LL * size * size * static_cast<long long>(sizeof(double))
             << '\n';
    } catch (const exception& error) {
        cerr << "Error: " << error.what() << '\n';
        return 1;
    }

    return 0;
}
