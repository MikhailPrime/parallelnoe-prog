@echo off
setlocal
cd /d "%~dp0"

cl /EHsc /O2 /openmp /std:c++17 main.cpp /Fe:matrix.exe
if errorlevel 1 (
    echo Compilation failed.
    exit /b 1
)

py -m pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency installation failed.
    exit /b 1
)

py experiment.py --exe .\matrix.exe
if errorlevel 1 (
    echo Experiment failed.
    exit /b 1
)

echo Experiments completed.
