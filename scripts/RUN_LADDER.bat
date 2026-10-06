@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
set PYTHONDONTWRITEBYTECODE=1
set PYTHONUTF8=1
set PY=python
where py >nul 2>nul && set PY=py -3
echo === Model / context / index ladder on THIS machine (same harness, same data, prompt v2) ===
echo Downloads if missing: qwen2.5:0.5b (~0.4 GB), qwen2.5:7b (~4.7 GB), nomic-embed-text (~0.3 GB)
echo All three are Apache-2.0. qwen2.5:3b is skipped on purpose (Qwen Research License, non-commercial).
%PY% -B -W ignore -m unittest discover -s tests || goto :fail
ollama pull qwen2.5:0.5b || goto :fail
ollama pull qwen2.5:7b || goto :fail
ollama pull nomic-embed-text || goto :fail
echo [1] model size on the default 2048 context (1.5b already has R = 3)
for %%C in (K1 F2) do (
  %PY% -B -m tracedraft run --case %%C --style prose --selector fcea --adapter ollama --model qwen2.5:0.5b --prompt v2
  %PY% -B -m tracedraft run --case %%C --style prose --selector fcea --adapter ollama --model qwen2.5:7b --prompt v2
)
echo [2] larger context: does a big window make contract-aware assembly unnecessary?
for %%C in (K1 F2) do (
  %PY% -B -m tracedraft run --case %%C --style prose --selector topk --adapter ollama --model qwen2.5:7b --prompt v2 --num-ctx 8192
  %PY% -B -m tracedraft run --case %%C --style prose --selector fcea --adapter ollama --model qwen2.5:7b --prompt v2 --num-ctx 8192
)
echo [3] hybrid index: lexical (BM25 + trigram) vs lexical + small embedding model
for %%C in (K1 F2) do %PY% -B -m tracedraft run --case %%C --style prose --selector fcea --adapter ollama --model qwen2.5:1.5b --prompt v2 --dense nomic-embed-text
echo [4] optional: qwen2.5:14b (~9 GB, partly in system RAM on an 8 GB GPU; 20-40 min)
choice /C YN /T 20 /D N /M "Run 14b too"
if errorlevel 2 goto :front
ollama pull qwen2.5:14b || goto :front
for %%C in (K1 F2) do %PY% -B -m tracedraft run --case %%C --style prose --selector fcea --adapter ollama --model qwen2.5:14b --prompt v2
:front
echo [5] routing front over models measured on this machine (per field: rules / 0.5b / 1.5b / 7b ...)
for %%C in (K1 F2) do %PY% -B -m tracedraft optimize --case %%C --style prose --epsilon 0 --tier laptop > nul
echo Done. Every run records CPU, RAM, GPU and how much of the model sat in VRAM (config.json: env.hw, ollama_residency).
pause
exit /b 0
:fail
echo Self-test or model download failed; stopped.
pause
exit /b 1
