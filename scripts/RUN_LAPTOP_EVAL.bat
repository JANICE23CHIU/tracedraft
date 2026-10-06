@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
set PYTHONDONTWRITEBYTECODE=1
set PYTHONUTF8=1
set PY=python
where py >nul 2>nul && set PY=py -3
set MODEL=qwen2.5:1.5b
echo === TraceDraft Stage I evaluation on this laptop (Ollama stand-in for UGen300) ===
echo [0] tests
%PY% -B -m unittest discover -s tests
echo [1] is Ollama reachable?
%PY% -B -m tracedraft ping --adapter ollama --model %MODEL%
echo [2] no-model baseline
%PY% -B -m tracedraft demo > runs_demo_summary.json
for %%C in (K1 F2) do (
  echo [3] %%C prose: extraction, FCEA vs top-k
  %PY% -B -m tracedraft run --case %%C --style prose --selector fcea --adapter ollama --model %MODEL% --llm-mode review
  %PY% -B -m tracedraft run --case %%C --style prose --selector topk --adapter ollama --model %MODEL% --llm-mode review
  echo [4] %%C prose: citation verifier, model alone and combined
  %PY% -B -m tracedraft verifier-eval --case %%C --style prose --adapter ollama --model %MODEL% --llm-mode all
  %PY% -B -m tracedraft verifier-eval --case %%C --style prose --adapter ollama --model %MODEL% --llm-mode review
)
echo.
echo Done. Results: runs\LEDGER.jsonl  (send this file back; every line points to a sealed run folder)
pause
