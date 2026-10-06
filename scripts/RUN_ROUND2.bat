@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
set PYTHONDONTWRITEBYTECODE=1
set PYTHONUTF8=1
set PY=python
where py >nul 2>nul && set PY=py -3
set MODEL=qwen2.5:1.5b
echo === Round 2/3 (ratchet: one change per round). Dev case K1, held-out F2, held-out phrasing proseB ===
%PY% -B -W ignore -m unittest discover -s tests
echo [R2] prompt v2 = short evidence handles  (only change vs round 1)
%PY% -B -m tracedraft run --case K1 --style prose --selector fcea --adapter ollama --model %MODEL% --prompt v2
echo [R3] prompt v3 = v2 + contract cue words (only change vs R2)
%PY% -B -m tracedraft run --case K1 --style prose --selector fcea --adapter ollama --model %MODEL% --prompt v3
echo [Held-out] same three prompts on F2 and on the held-out phrasing (proseB), FCEA and top-k
for %%P in (v1 v2 v3) do (
  %PY% -B -m tracedraft run --case F2 --style prose  --selector fcea --adapter ollama --model %MODEL% --prompt %%P
  %PY% -B -m tracedraft run --case K1 --style proseB --selector fcea --adapter ollama --model %MODEL% --prompt %%P
  %PY% -B -m tracedraft run --case F2 --style proseB --selector fcea --adapter ollama --model %MODEL% --prompt %%P
)
%PY% -B -m tracedraft run --case K1 --style proseB --selector topk --adapter ollama --model %MODEL% --prompt v3
%PY% -B -m tracedraft run --case F2 --style proseB --selector topk --adapter ollama --model %MODEL% --prompt v3
echo [Verifier] model alone vs layered, held-out phrasing
for %%C in (K1 F2) do (
  %PY% -B -m tracedraft verifier-eval --case %%C --style proseB --adapter ollama --model %MODEL% --llm-mode all
  %PY% -B -m tracedraft verifier-eval --case %%C --style proseB --adapter ollama --model %MODEL% --llm-mode review
)
echo.
echo Done. Results are appended to runs\LEDGER.jsonl
pause
